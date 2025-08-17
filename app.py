#!/usr/bin/python3
import os
import sys
import time
import json
import shutil
import errno
import requests
import zipfile
import urllib3
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import getpass

# Flask API for deployment endpoint
try:
    from flask import Flask, request, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
if FLASK_AVAILABLE:
    app = Flask(__name__)

    @app.route('/deploy', defaults={'filename': None}, methods=['GET'], strict_slashes=False)  # ללא סלאש
    @app.route('/deploy/', defaults={'filename': None}, methods=['GET'], strict_slashes=False)  # עם סלאש
    @app.route('/deploy/<filename>', methods=['GET'], strict_slashes=False)  # עם שם קובץ
    def deploy_config(filename):
        # If no filename provided, return usage instructions
        if not filename:
            # Get the full URL for the endpoint
            base_url = request.url_root.rstrip('/')
            usage_guide = {
                'success': False,
                'message': 'Missing filename parameter',
                'usage': {
                    'base_url': base_url,
                    'full_endpoint': f"{base_url}/deploy/<filename>",
                    'endpoint': '/deploy/<filename>',
                    'method': 'GET',
                    'required_parameters': {
                        'filename': 'Name of the configuration file (must exist in processed directory)'
                    },
                    'optional_parameters': {
                        'RUN_SETUP_SCRIPT': {
                            'type': 'boolean',
                            'default': False,
                            'description': 'Whether to run setup.sh after deployment',
                            'valid_values': ['true', 'false', '1', '0', 'yes', 'no']
                        },
                        'UPDATE_ONLY_CHANGED_FILES': {
                            'type': 'boolean',
                            'default': True,
                            'description': 'Whether to update only changed files or perform full deployment',
                            'valid_values': ['true', 'false', '1', '0', 'yes', 'no']
                        }
                    },
                    'example': '/deploy/my_config.json?RUN_SETUP_SCRIPT=true&UPDATE_ONLY_CHANGED_FILES=true'
                }
            }
            return jsonify(usage_guide), 400

        run_setup_script = request.args.get('RUN_SETUP_SCRIPT')
        update_only_changed_files = request.args.get('UPDATE_ONLY_CHANGED_FILES')

        # Parse boolean values from query string
        def parse_bool(val):
            if val is None:
                return None
            if isinstance(val, bool):
                return val
            return str(val).lower() in ['1', 'true', 'yes']

        run_setup_script = parse_bool(run_setup_script)
        update_only_changed_files = parse_bool(update_only_changed_files)

        src = os.path.join(CONFIG_PROCESSED_DIR, filename)
        dst = os.path.join(CONFIG_WATCH_DIR, filename)
        
        # Check if the file exists and provide guidance
        if not os.path.exists(src):
            error_response = {
                'success': False,
                'message': f'File {filename} not found in processed directory',
                'help': {
                    'possible_issues': [
                        'The file name might be incorrect',
                        'The file might not be processed yet',
                        'The file might have been deleted'
                    ],
                    'what_to_do': [
                        'Check if the filename is correct',
                        'Ensure the configuration file exists in the processed directory',
                        'Try processing the configuration file first'
                    ],
                    'available_files': os.listdir(CONFIG_PROCESSED_DIR) if os.path.exists(CONFIG_PROCESSED_DIR) else []
                }
            }
            log_message(f"קובץ {filename} לא נמצא ב-processed")
            return jsonify(error_response), 400
        try:
            # קריאת הקובץ ועדכון פרמטרים אם צריך
            with open(src, 'r', encoding='utf-8') as f:
                config = json.load(f)
            changed = False
            if run_setup_script is not None:
                config['run_setup_script'] = run_setup_script
                changed = True
            if update_only_changed_files is not None:
                config['update_only_changed_files'] = update_only_changed_files
                changed = True
            if changed:
                with open(src, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
            shutil.move(src, dst)
            log_message(f"הקובץ {filename} הועבר מ-processed ל-pending בהצלחה")
            return jsonify({'success': True, 'message': 'Moved successfully'}), 200
        except Exception as e:
            log_message(f"שגיאה בהעברת קובץ {filename}: {str(e)}")
            return jsonify({'success': False, 'message': str(e)}), 400


# התעלמות מאזהרות SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# הגדרות מערכת
BASE_DIR = "/var/www/html/CornGetFromGit"
CONFIG_WATCH_DIR = f"{BASE_DIR}/pending"  # תיקייה לקבצי הגדרות חדשים
CONFIG_PROCESSED_DIR = f"{BASE_DIR}/processed"  # תיקייה לקבצים שעובדו
LOG_FILE = f"{BASE_DIR}/log.log"
STATE_FILE = f"{BASE_DIR}/last_commit.json"

# מרווחי זמן לבדיקות
AUTO_CHECK_INTERVAL = 1200   # בדיקת GitHub כל 20 דקות

# הגדרות ברירת מחדל
REPO_OWNER = None
REPO_NAME = None
DEPLOY_PATH = None
GITHUB_TOKEN = ""
UPDATE_ONLY_CHANGED_FILES = True
BRANCH = 'main'  # ברירת מחדל
RUN_SETUP_SCRIPT = False  # ברירת מחדל להרצת setup.sh

class ConfigFileHandler(FileSystemEventHandler):
    """מטפל באירועים של קבצים חדשים בתיקיית pending"""
    
    def __init__(self):
        self.processing = set()  # מעקב אחר קבצים בעיבוד
    
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.json'):
            if event.src_path not in self.processing:
                self.processing.add(event.src_path)
                log_message(f"זוהה קובץ הגדרות חדש: {event.src_path}")
                process_config_file(event.src_path)
                self.processing.remove(event.src_path)
    
    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith('.json'):
            if event.src_path not in self.processing and os.path.exists(event.src_path):
                self.processing.add(event.src_path)
                log_message(f"זוהה עדכון בקובץ הגדרות: {event.src_path}")
                process_config_file(event.src_path)
                self.processing.remove(event.src_path)

def log_message(message, command_output=None):
    """כותב הודעה לקובץ לוג ולמסך"""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    
    # הדפסה למסך
    print(log_entry)
    
    try:
        # כתיבה לקובץ עם קידוד utf-8
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry + "\n")
            if command_output:
                f.write(f"Command output:\n{command_output}\n")
                f.write("-" * 50 + "\n")
    except Exception as e:
        print(f"[{timestamp}] שגיאה בכתיבה לקובץ לוג: {str(e)}")

def run_command(command):
    """מריץ פקודה ומחזיר את התוצאה והקוד"""
    try:
        # הרצת הפקודה דרך /bin/bash כדי לשמור על הגדרות ה-sudo
        process = subprocess.run(['/bin/bash', '-c', command], 
                               capture_output=True, 
                               text=True)
        output = process.stdout + process.stderr
        return_code = process.returncode
        
        log_message(f"הרצת פקודה: {command}", 
                   f"Return code: {return_code}\nOutput:\n{output}")
        return return_code, output
    except Exception as e:
        error_msg = f"שגיאה בהרצת פקודה {command}: {str(e)}"
        log_message(error_msg)
        return -1, error_msg

def get_latest_commit():
    """מקבל את המזהה של הקומיט האחרון"""
    api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/{BRANCH}"  # שימוש בענף הנבחר
    headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}
    response = requests.get(api_url, headers=headers, verify=False)
    if response.status_code == 200:
        return response.json()['sha']
    return None

def save_state(commit_sha):
    """שומר את מזהה הקומיט האחרון"""
    try:
        # יצירת התיקייה אם היא לא קיימת
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        
        # אם אין קומיט, נשמור אובייקט ריק
        data = {'last_commit': commit_sha} if commit_sha else {}
        
        with open(STATE_FILE, 'w') as f:
            json.dump(data, f)
        
        if commit_sha:
            log_message(f"עודכן קובץ המצב: {commit_sha}")
        return True
    except Exception as e:
        log_message(f"שגיאה בשמירת המצב: {str(e)}")
        return False

def load_state():
    """טוען את מזהה הקומיט האחרון"""
    try:
        if not os.path.exists(STATE_FILE) or os.path.getsize(STATE_FILE) == 0:
            return None
            
        with open(STATE_FILE, 'r') as f:
            try:
                data = json.load(f)
                return data.get('last_commit')
            except json.JSONDecodeError:
                # אם הקובץ קיים אבל לא תקין, נאפס אותו
                save_state(None)
                return None
    except Exception as e:
        log_message(f"שגיאה בטעינת המצב: {str(e)}")
        return None

def get_commits_between(base_commit, head_commit):
    """מחזיר רשימת מזהי קומיטים מהישן לחדש (לא כולל base, כולל head)"""
    try:
        commits = []
        page = 1
        while True:
            api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits?sha={BRANCH}&since=&per_page=100&page={page}"
            headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}
            response = requests.get(api_url, headers=headers, verify=False)
            if response.status_code != 200:
                log_message(f"שגיאה בקבלת רשימת קומיטים: {response.status_code}")
                return []
            data = response.json()
            if not data:
                break
            for commit in data:
                sha = commit['sha']
                commits.append(sha)
                if sha == base_commit:
                    # עצרנו, base_commit נמצא
                    return list(reversed(commits[:-1]))  # לא כולל base, מהישן לחדש
            page += 1
        return list(reversed(commits))
    except Exception as e:
        log_message(f"שגיאה בקבלת קומיטים בטווח: {str(e)}")
        return []

def deploy_latest_version():
    """מוריד ופורס את הגרסה האחרונה, ומעתיק רק קבצים ששונו בכל הקומיטים מהפעם האחרונה"""
    try:
        log_message("מתחיל תהליך התקנה...")
        current_commit = get_latest_commit()  # שמירת הקומיט הנוכחי
        last_known_commit = load_state()
        # שינוי כתובת ה-ZIP להשתמש בענף הנכון
        zip_url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/{BRANCH}.zip"
        headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}
        response = requests.get(zip_url, headers=headers, verify=False)
        if response.status_code == 200:
            log_message("הורדת הקבצים הצליחה")
            zip_path = '/tmp/repo.zip'
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            log_message(f"קובץ ZIP נשמר ב-{zip_path}")
            extracted_dir = f"/tmp/{REPO_NAME}-{BRANCH}"
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall('/tmp')
            log_message("קבצים חולצו בהצלחה")
            if UPDATE_ONLY_CHANGED_FILES and last_known_commit:
                # אם יש שינוי, ניקח את כל הקבצים מכל הקומיטים בטווח; אם אין שינוי, רק את הקומיט האחרון
                if current_commit != last_known_commit:
                    commits = get_commits_between(last_known_commit, current_commit)
                    commits.append(current_commit)
                else:
                    commits = [current_commit]
                changed_files = set()
                for sha in commits:
                    for file in get_changed_files(sha):
                        changed_files.add(file)
                # העברה למיקום הסופי רק של הקבצים ששונו (הגרסה האחרונה מה-ZIP)
                for file in changed_files:
                    src = os.path.join(extracted_dir, file)
                    dst = os.path.join(DEPLOY_PATH, file)
                    dst_dir = os.path.dirname(dst)
                    if not os.path.exists(dst_dir):
                        os.makedirs(dst_dir, exist_ok=True)
                    if os.path.exists(src):
                        run_command(f"sudo -n mv '{src}' '{dst}'")
            else:
                run_command(f"sudo -n rm -rf {DEPLOY_PATH}/*")
                run_command(f"sudo -n mv {extracted_dir}/* {DEPLOY_PATH}/")
            run_command(f"sudo -n chown -R www-data:www-data {DEPLOY_PATH}")
            setup_success = True
            if os.path.exists(f"{DEPLOY_PATH}/setup.sh"):
                current_dir = os.getcwd()
                os.chdir(DEPLOY_PATH)
                run_command("sudo chmod +x setup.sh")
                log_message("מריץ את setup.sh")
                try:
                    if RUN_SETUP_SCRIPT:
                        process = os.popen(f"sudo -n {DEPLOY_PATH}/setup.sh production 2>&1")
                        output = process.read()
                        install_result = process.close()
                    else:
                        install_result = os.system("./setup.sh")
                        output = "הרצה הושלמה" if install_result == 0 else f"נכשל עם קוד שגיאה: {install_result}"
                    if install_result == 0:
                        log_message("setup.sh הסתיים בהצלחה")
                        log_message(f"פלט:\n{output}")
                    else:
                        error_code = install_result >> 8
                        log_message(f"שגיאה בהרצת setup.sh. קוד שגיאה: {error_code}")
                        log_message(f"פלט:\n{output}")
                        setup_success = False
                except Exception as e:
                    log_message(f"שגיאה בהרצת setup.sh: {str(e)}")
                    setup_success = False
                os.chdir(current_dir)
            else:
                log_message("קובץ setup.sh לא נמצא")
            save_state(current_commit)
            log_message("התקנה הושלמה" + (" בהצלחה" if setup_success else " עם שגיאות ב-setup.sh"))
            return True
    except Exception as e:
        log_message(f"שגיאה בתהליך ההתקנה: {str(e)}")
        return False
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(extracted_dir):
            run_command(f"sudo -n rm -rf {extracted_dir}")

def load_config(config_file):
    """טוען הגדרות מקובץ"""
    global REPO_OWNER, REPO_NAME, DEPLOY_PATH, GITHUB_TOKEN, UPDATE_ONLY_CHANGED_FILES, BRANCH, RUN_SETUP_SCRIPT
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            REPO_OWNER = config['repo_owner']
            REPO_NAME = config['repo_name']
            DEPLOY_PATH = config['deploy_path']
            GITHUB_TOKEN = config.get('github_token', '')
            UPDATE_ONLY_CHANGED_FILES = config.get('update_only_changed_files', False)
            BRANCH = config.get('branch', 'main')  # קריאת הענף מההגדרות
            RUN_SETUP_SCRIPT = config.get('run_setup_script', False)  # קריאת הגדרת הרצת setup.sh
            return True
    except Exception as e:
        log_message(f"שגיאה בטעינת הגדרות מ-{config_file}: {str(e)}")
        return False

def run_single_check(config_file=None):
    """פונקציה שמבצעת בדיקה אחת ומסתיימת"""
    try:
        if config_file and not load_config(config_file):
            return False
        
        if not REPO_OWNER or not REPO_NAME:
            log_message("חסרות הגדרות בסיסיות (REPO_OWNER, REPO_NAME)")
            return False

        current_commit = get_latest_commit()
        if not current_commit:
            log_message("לא הצלחתי לקבל את הקומיט האחרון")
            return False
        
        last_known_commit = load_state()
        log_message(f"קומיט נוכחי: {current_commit}, קומיט אחרון ידוע: {last_known_commit}")

        if UPDATE_ONLY_CHANGED_FILES:
            # תמיד נבצע פריסה של הקבצים ששונו בקומיט האחרון (או בטווח)
            deploy_latest_version()
            # נשמור את הקומיט רק אם יש שינוי
            if current_commit != last_known_commit:
                save_state(current_commit)
            return True
        else:
            # תמיד פריסה מלאה
            deploy_latest_version()
            if current_commit != last_known_commit:
                save_state(current_commit)
            return True
        return False
    except Exception as e:
        log_message(f"שגיאה: {str(e)}")
        return False

def check_permissions():
    """בדיקה והגדרת הרשאות לתיקיות ולקבצים"""
    try:
        # בדיקת הרשאות לתיקיות
        for dir_path in [BASE_DIR, CONFIG_WATCH_DIR, CONFIG_PROCESSED_DIR]:
            if not os.access(dir_path, os.W_OK):
                log_message(f"אין הרשאות כתיבה לתיקייה: {dir_path}")
                return False
        
        # בדיקת הרשאות לקבצים
        for file_path in [LOG_FILE, STATE_FILE]:
            dir_path = os.path.dirname(file_path)
            if not os.access(dir_path, os.W_OK):
                log_message(f"אין הרשאות כתיבה לתיקייה: {dir_path}")
                return False
            if os.path.exists(file_path) and not os.access(file_path, os.W_OK):
                log_message(f"אין הרשאות כתיבה לקובץ: {file_path}")
                return False
        
        return True
    except Exception as e:
        log_message(f"שגיאה בבדיקת הרשאות: {str(e)}")
        return False

def validate_config(config):
    """בדיקת תקינות קובץ ההגדרות"""
    required_fields = [
        'repo_owner',
        'repo_name',
        'deploy_path'
    ]
    
    optional_fields = {
        'github_token': '',
        'branch': 'main',
        'setup_script': 'setup.sh',
        'setup_args': 'production',
        'run_setup_script': False  # הוספת שדה חדש עם ערך ברירת מחדל False
    }
    
    # בדיקת שדות חובה
    for field in required_fields:
        if field not in config:
            log_message(f"שגיאה: חסר שדה חובה {field}")
            return False
        if not config[field]:
            log_message(f"שגיאה: שדה {field} ריק")
            return False
    
    # הוספת שדות אופציונליים עם ערכי ברירת מחדל
    for field, default_value in optional_fields.items():
        if field not in config or not config[field]:
            config[field] = default_value
    
    return True

def process_config_file(config_file_path):
    """מעבד קובץ הגדרות ומבצע התקנה"""
    try:
        log_message(f"מתחיל עיבוד קובץ: {config_file_path}")
        
        # טעינת הגדרות חדשות
        with open(config_file_path, 'r') as f:
            config = json.load(f)
        
        # בדיקת תקינות ההגדרות
        if not validate_config(config):
            log_message(f"קובץ {config_file_path} מכיל הגדרות לא תקינות")
            if os.path.exists(config_file_path):
                os.remove(config_file_path)  # מחיקת הקובץ
            return False
        
        # הכנת הקובץ החדש
        processed_file = os.path.join(CONFIG_PROCESSED_DIR, 
                                    os.path.basename(config_file_path))
        
        try:
            # ביצוע ההתקנה
            success = run_single_check(config_file_path)
            current_commit = get_latest_commit()
            
            # הוספת מידע על ההתקנה
            update_info = {
                'last_commit': current_commit,
                'last_update': time.strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'success',
                'update_log': "אין צורך בעדכון - הגרסה העדכנית כבר מותקנת"
            }
            
            if success and current_commit != load_state():
                update_info['update_log'] = "התקנה הושלמה בהצלחה"
            elif not success:
                update_info['status'] = 'failed'
                update_info['update_log'] = "התקנה נכשלה"
            
            # עדכון הקונפיג עם המידע החדש
            config.update(update_info)
            
            # כתיבת התוכן לקובץ החדש אם ההתקנה הצליחה
            if success:
                with open(processed_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
                log_message(f"קובץ {config_file_path} הועבר בהצלחה ל-processed")
            else:
                log_message(f"התקנה נכשלה עבור {config_file_path}")
            
            # מחיקת הקובץ המקורי בכל מקרה
            if os.path.exists(config_file_path):
                try:
                    os.remove(config_file_path)
                except Exception as e:
                    log_message(f"שגיאה במחיקת קובץ המקור: {str(e)}")
            
            return success
            
        except Exception as e:
            log_message(f"שגיאה בעיבוד קובץ: {str(e)}")
            if os.path.exists(config_file_path):
                try:
                    os.remove(config_file_path)  # מחיקת הקובץ גם במקרה של שגיאה
                except:
                    pass
            return False
            
    except Exception as e:
        log_message(f"שגיאה בעיבוד קובץ הגדרות {config_file_path}: {str(e)}")
        if os.path.exists(config_file_path):
            try:
                os.remove(config_file_path)  # מחיקת הקובץ גם במקרה של שגיאה
            except:
                pass
        return False

def check_processed_configs():
    """בדיקת עדכונים לקבצי הגדרות מעובדים"""
    try:
        # בדיקה אם יש תהליך התקנה פעיל
        if os.name == 'nt':  # Windows
            try:
                import psutil
                for proc in psutil.process_iter(['pid', 'name']):
                    if 'setup.sh' in proc.info['name'] or 'app.py' in proc.info['name']:
                        log_message(f"יש תהליך התקנה פעיל (PID: {proc.info['pid']})")
                        return
            except ImportError:
                log_message("psutil לא מותקן, לא ניתן לבדוק תהליכים פעילים")
                return
        else:  # Linux/Unix
            try:
                output = subprocess.check_output(['pgrep', '-f', 'setup.sh|app.py']).decode()
                if output.strip():
                    log_message("זוהה תהליך התקנה פעיל, דילוג על בדיקת עדכונים")
                    return
            except subprocess.CalledProcessError:
                pass  # אין תהליך התקנה פעיל
        
        log_message("מתחיל בדיקה תקופתית...")
        
        if not os.path.exists(CONFIG_PROCESSED_DIR):
            log_message("תיקיית processed לא קיימת") 
            return
            
        files = [f for f in os.listdir(CONFIG_PROCESSED_DIR) if f.endswith('.json')]
        if not files:
            log_message("אין קבצי הגדרות בתיקיית processed")
            return
            
        log_message(f"נמצאו {len(files)} קבצי הגדרות לבדיקה")
        
        for file in files:
            try:
                config_path = os.path.join(CONFIG_PROCESSED_DIR, file)
                log_message(f"בודק עדכונים עבור {file}...")
                
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    
                # טעינת הגדרות גלובליות
                global REPO_OWNER, REPO_NAME, DEPLOY_PATH, GITHUB_TOKEN, RUN_SETUP_SCRIPT
                REPO_OWNER = config['repo_owner']
                REPO_NAME = config['repo_name']
                DEPLOY_PATH = config['deploy_path']
                GITHUB_TOKEN = config.get('github_token', '')
                RUN_SETUP_SCRIPT = config.get('run_setup_script', False)
                
                # בדיקת עדכונים
                current_commit = get_latest_commit()
                last_known_commit = load_state()  # קריאת הקומיט האחרון מקובץ המצב
                
                log_message(f"קומיט נוכחי: {current_commit}, קומיט אחרון ידוע: {last_known_commit}")
                
                if not current_commit:
                    log_message(f"לא הצלחתי לקבל את הקומיט האחרון עבור {file}")
                    continue
                    
                if current_commit != last_known_commit:
                    log_message(f"נמצא עדכון חדש עבור {file}")
                    if deploy_latest_version():
                        # עדכון הקומיט האחרון בשני המקומות
                        save_state(current_commit)  # שמירה בקובץ המצב הגלובלי
                        
                        # עדכון בקובץ ההגדרות
                        config['last_commit'] = current_commit
                        config['last_update'] = time.strftime('%Y-%m-%d %H:%M:%S')
                        config['status'] = 'success'
                        config['update_log'] = "התקנה הושלמה בהצלחה"
                        
                        # שמירת הקובץ המעודכן
                        with open(config_path, 'w', encoding='utf-8') as f:
                            json.dump(config, f, indent=4, ensure_ascii=False)
                            
                        log_message(f"עודכן קובץ {file} וקובץ המצב הגלובלי")
                else:
                    log_message(f"אין עדכונים חדשים עבור {file}")
                    
            except Exception as e:
                log_message(f"שגיאה בבדיקת {file}: {str(e)}")
                continue
                
    except Exception as e:
        log_message(f"שגיאה בבדיקת עדכונים אוטומטית: {str(e)}")

def acquire_lock():
    """מנסה לקבל נעילה על הסקריפט"""
    lock_file = os.path.join(BASE_DIR, 'check_updates.lock')
    
    # ייבוא מותנה לפי מערכת ההפעלה
    if os.name == 'nt':
        import msvcrt
    else:
        import fcntl

    try:
        # בדיקת תהליכים קיימים
        if os.name == 'nt':  # Windows
            try:
                if os.path.exists(lock_file):
                    with open(lock_file, 'r') as f:
                        lock_data = json.load(f)
                        # בדיקה אם התהליך עדיין רץ
                        pid = lock_data.get('pid')
                        if pid:
                            try:
                                import psutil
                                if psutil.pid_exists(pid):
                                    log_message(f"יש תהליך התקנה פעיל (PID: {pid})")
                                    return None
                            except ImportError:
                                # אם psutil לא מותקן, נבדוק לפי זמן
                                if time.time() - os.path.getmtime(lock_file) < 3600:  # שעה אחת
                                    return None
                    # אם הגענו לכאן, הקובץ ישן או לא תקין
                    os.remove(lock_file)
            except Exception:
                pass

            # יצירת קובץ נעילה חדש
            try:
                fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except OSError as e:
                if e.errno == errno.EEXIST:
                    return None
                raise
            f = os.fdopen(fd, 'w')
        else:  # Linux/Unix
            # בדיקת תהליכים קיימים
            try:
                output = subprocess.check_output(['pgrep', '-f', 'setup.sh|app.py']).decode()
                pids = output.strip().split('\n')
                current_pid = str(os.getpid())
                other_pids = [pid for pid in pids if pid != current_pid]
                
                if other_pids:
                    log_message(f"יש תהליך התקנה פעיל (PIDs: {', '.join(other_pids)})")
                    return None
            except subprocess.CalledProcessError:
                pass

            f = open(lock_file, 'w')
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except IOError:
                f.close()
                return None

        # כתיבת מידע לקובץ הנעילה
        info = {
            'pid': os.getpid(),
            'start_time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'user': getpass.getuser()
        }
        json.dump(info, f)
        f.flush()
        
        log_message(f"נעילה הושגה בהצלחה (PID: {os.getpid()})")
        return f
        
    except Exception as e:
        log_message(f"שגיאה בנעילת הקובץ: {str(e)}")
        return None

def release_lock(lock_fd):
    """משחרר את הנעילה"""
    try:
        if lock_fd:
            if os.name == 'nt':  # Windows
                lock_fd.close()
                try:
                    os.remove(os.path.join(BASE_DIR, 'check_updates.lock'))
                except:
                    pass
            else:  # Linux/Unix
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                lock_fd.close()
                try:
                    os.remove(os.path.join(BASE_DIR, 'check_updates.lock'))
                except:
                    pass
    except Exception as e:
        log_message(f"שגיאה בשחרור הנעילה: {str(e)}")

def validate_directories():
    """בדיקת תקינות התיקיות"""
    try:
        # וידוא שהתיקיות קיימות
        for dir_path in [BASE_DIR, CONFIG_WATCH_DIR, CONFIG_PROCESSED_DIR, os.path.dirname(LOG_FILE), os.path.dirname(STATE_FILE)]:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
                log_message(f"נוצרה תיקייה: {dir_path}")
        
        # בדיקת תכולת pending
        pending_files = [f for f in os.listdir(CONFIG_WATCH_DIR) if f.endswith('.json')]
        if pending_files:
            log_message(f"נמצאו {len(pending_files)} קבצים בתיקיית pending")
            for file in pending_files:
                log_message(f"מעבד קובץ שנשאר: {file}")
                process_config_file(os.path.join(CONFIG_WATCH_DIR, file))
        
        return True
    except Exception as e:
        log_message(f"שגיאה בבדיקת תיקיות: {str(e)}")
        return False

def get_changed_files(commit_sha):
    """מקבל רשימת קבצים ששונו בקומיט מסוים"""
    try:
        # קבלת מידע על הקומיט
        api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/{commit_sha}"
        headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}
        
        response = requests.get(api_url, headers=headers, verify=False)
        if response.status_code != 200:
            log_message(f"שגיאה בקבלת מידע על קומיט: {response.status_code}")
            return []
            
        commit_data = response.json()
        changed_files = []
        
        # איסוף רשימת הקבצים ששונו
        for file in commit_data.get('files', []):
            file_path = file.get('filename')
            if file_path:
                # יצירת תיקיות נדרשות
                dir_path = os.path.dirname(os.path.join(DEPLOY_PATH, file_path))
                if not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)
                changed_files.append(file_path)
        
        log_message(f"נמצאו {len(changed_files)} קבצים ששונו בקומיט {commit_sha}")
        return changed_files
        
    except Exception as e:
        log_message(f"שגיאה בקבלת רשימת קבצים ששונו: {str(e)}")
        return []

def main():
    # בדיקת תקינות התיקיות לפני כל פעולה
    if not validate_directories():
        print("שגיאה: לא ניתן לוודא תקינות תיקיות")
        return False

    # ניסיון לקבל נעילה (כולל בדיקת תהליכים כפולים)
    lock_fd = acquire_lock()
    if not lock_fd:
        return False

    try:
        if not check_permissions():
            print("שגיאה: לא ניתן להגדיר הרשאות נדרשות")
            return False

        if len(sys.argv) > 1 and sys.argv[1] == "--single":
            return run_single_check()
        
        log_message("התחלת מעקב אחר שינויים...")
        
        # הגדרת מאזין לתיקיית pending
        event_handler = ConfigFileHandler()
        observer = Observer()
        observer.schedule(event_handler, CONFIG_WATCH_DIR, recursive=False)
        observer.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            observer.join()
    finally:
        release_lock(lock_fd)

def start_watcher():
    """מפעיל את ה-Watcher בתהליך נפרד"""
    try:
        if not validate_directories():
            log_message("שגיאה: לא ניתן לוודא תקינות תיקיות")
            return False

        lock_fd = acquire_lock()
        if not lock_fd:
            return False

        if not check_permissions():
            log_message("שגיאה: לא ניתן להגדיר הרשאות נדרשות")
            return False

        log_message("התחלת מעקב אחר שינויים...")
        event_handler = ConfigFileHandler()
        observer = Observer()
        observer.schedule(event_handler, CONFIG_WATCH_DIR, recursive=False)
        observer.start()
        return observer
    except Exception as e:
        log_message(f"שגיאה בהפעלת Watcher: {str(e)}")
        return None

# הפעלת Watcher כשמריצים עם Gunicorn
if FLASK_AVAILABLE:
    observer = start_watcher()

if __name__ == '__main__':
    current_user = getpass.getuser()
    log_message(f"הסקריפט רץ תחת המשתמש: {current_user}")
    if FLASK_AVAILABLE and len(sys.argv) > 1 and sys.argv[1] == '--api':
        app.run(host='0.0.0.0', port=5000)
    else:
        sys.exit(0 if main() else 1)
