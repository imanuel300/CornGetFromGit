#!/usr/bin/python3

import requests
import zipfile
import os
import time
import json
import urllib3
import sys
import subprocess
import fcntl
import errno
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# התעלמות מאזהרות SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# הגדרות מערכת
BASE_DIR = "/var/www/html/CornGetFromGit"
CONFIG_WATCH_DIR = f"{BASE_DIR}/pending"  # תיקייה לקבצי הגדרות חדשים
CONFIG_PROCESSED_DIR = f"{BASE_DIR}/processed"  # תיקייה לקבצים שעובדו
LOG_FILE = f"{BASE_DIR}/update_process.log"
STATE_FILE = f"{BASE_DIR}/last_commit.json"

# מרווחי זמן לבדיקות
AUTO_CHECK_INTERVAL = 600   # בדיקת GitHub כל 10 דקות

# הגדרות ברירת מחדל
REPO_OWNER = None
REPO_NAME = None
DEPLOY_PATH = None
GITHUB_TOKEN = ""
UPDATE_ONLY_CHANGED_FILES = False
BRANCH = 'main'  # ברירת מחדל

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
        # כתיבה לקובץ
        with open(LOG_FILE, 'a') as f:
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

def deploy_latest_version():
    """מוריד ופורס את הגרסה האחרונה"""
    try:
        log_message("מתחיל תהליך התקנה...")
        
        # שינוי כתובת ה-ZIP להשתמש בענף הנכון
        zip_url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/{BRANCH}.zip"
        headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}
        response = requests.get(zip_url, headers=headers, verify=False)
        
        if response.status_code == 200:
            log_message("הורדת הקבצים הצליחה")
            
            # שמירת הקובץ ZIP
            zip_path = '/tmp/repo.zip'
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            log_message(f"קובץ ZIP נשמר ב-{zip_path}")
            
            # פריסת הקבצים - שים לב לשינוי בשם התיקייה
            extracted_dir = f"/tmp/{REPO_NAME}-{BRANCH}"  # שינוי שם התיקייה לפי הענף
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall('/tmp')
            log_message("קבצים חולצו בהצלחה")
            
            if UPDATE_ONLY_CHANGED_FILES:
                # קבלת רשימת הקבצים ששונו בקומיט האחרון
                changed_files = get_changed_files(get_latest_commit())
                
                # העברה למיקום הסופי רק של הקבצים ששונו
                for file in changed_files:
                    run_command(f"sudo -n mv {extracted_dir}/{file} {DEPLOY_PATH}/{file}")
            else:
                # העברה של כל הקבצים
                run_command(f"sudo -n rm -rf {DEPLOY_PATH}/*")
                run_command(f"sudo -n mv {extracted_dir}/* {DEPLOY_PATH}/")
            
            run_command(f"sudo -n chown -R www-data:www-data {DEPLOY_PATH}")
            
            # הרצת setup.sh אם קיים
            if os.path.exists(f"{DEPLOY_PATH}/setup.sh"):
                current_dir = os.getcwd()
                os.chdir(DEPLOY_PATH)
                run_command("sudo -n chmod +x setup.sh")
                # הרצה ישירה של setup.sh עם לוגים
                log_message("מריץ את setup.sh")
                # שימוש ב-os.popen כדי לקבל את הפלט
                process = os.popen("./setup.sh production 2>&1")
                output = process.read()
                install_result = process.close()
                
                if install_result is None:  # הצלחה
                    log_message("setup.sh הסתיים בהצלחה")
                else:
                    error_code = install_result >> 8  # המרה לקוד שגיאה אמיתי
                    log_message(f"שגיאה בהרצת setup.sh. קוד שגיאה: {error_code}")
                    log_message(f"פלט הסקריפט:\n{output}")
                os.chdir(current_dir)
            
            log_message("התקנה הושלמה בהצלחה")
            return True
        
    except Exception as e:
        log_message(f"שגיאה בתהליך ההתקנה: {str(e)}")
        return False
        
    finally:
        # ניקוי קבצים זמניים
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(extracted_dir):
            run_command(f"sudo -n rm -rf {extracted_dir}")

def load_config(config_file):
    """טוען הגדרות מקובץ"""
    global REPO_OWNER, REPO_NAME, DEPLOY_PATH, GITHUB_TOKEN, UPDATE_ONLY_CHANGED_FILES, BRANCH
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            REPO_OWNER = config['repo_owner']
            REPO_NAME = config['repo_name']
            DEPLOY_PATH = config['deploy_path']
            GITHUB_TOKEN = config.get('github_token', '')
            UPDATE_ONLY_CHANGED_FILES = config.get('update_only_changed_files', False)
            BRANCH = config.get('branch', 'main')  # קריאת הענף מההגדרות
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
        
        # אם אין קומיט ידוע, נשמור את הנוכחי ונחזיר הצלחה
        if not last_known_commit:
            log_message("אין קומיט ידוע קודם, שומר את הנוכחי")
            save_state(current_commit)
            return True
            
        if current_commit != last_known_commit:
            log_message("נמצא עדכון חדש")
            if deploy_latest_version():
                save_state(current_commit)
                return True
        else:
            log_message("אין עדכונים חדשים")
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
        'setup_args': 'production'
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
            try:
                os.remove(config_file_path)
            except Exception as e:
                log_message(f"שגיאה במחיקת קובץ המקור: {str(e)}")
            
            return success
            
        except Exception as e:
            log_message(f"שגיאה בעיבוד קובץ: {str(e)}")
            try:
                os.remove(config_file_path)  # מחיקת הקובץ גם במקרה של שגיאה
            except:
                pass
            return False
            
    except Exception as e:
        log_message(f"שגיאה בעיבוד קובץ הגדרות {config_file_path}: {str(e)}")
        try:
            os.remove(config_file_path)  # מחיקת הקובץ גם במקרה של שגיאה
        except:
            pass
        return False

def check_processed_configs():
    """בדיקת עדכונים לקבצי הגדרות מעובדים"""
    try:
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
                global REPO_OWNER, REPO_NAME, DEPLOY_PATH, GITHUB_TOKEN
                REPO_OWNER = config['repo_owner']
                REPO_NAME = config['repo_name']
                DEPLOY_PATH = config['deploy_path']
                GITHUB_TOKEN = config.get('github_token', '')
                
                # בדיקת עדכונים
                current_commit = get_latest_commit()
                # קריאת הקומיט האחרון מקובץ המצב הגלובלי
                last_known_commit = load_state()
                
                log_message(f"קומיט נוכחי: {current_commit}, קומיט אחרון ידוע: {last_known_commit}")
                
                if not current_commit:
                    log_message(f"לא הצלחתי לקבל את הקומיט האחרון עבור {file}")
                    continue
                    
                if current_commit != last_known_commit:
                    log_message(f"נמצא עדכון חדש עבור {file}")
                    if deploy_latest_version():
                        # עדכון הקומיט האחרון בשני המקומות
                        save_state(current_commit)
                        config['last_commit'] = current_commit
                        config['last_update'] = time.strftime('%Y-%m-%d %H:%M:%S')
                        config['status'] = 'success'
                        config['update_log'] = "התקנה הושלמה בהצלחה"
                        
                        with open(config_path, 'w') as f:
                            json.dump(config, f, indent=4, ensure_ascii=False)
                        log_message(f"עודכן קובץ {file}")
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
    try:
        # בדיקת תהליכים קיימים
        try:
            output = subprocess.check_output(['pgrep', '-f', 'check_updates.py']).decode()
            pids = output.strip().split('\n')
            current_pid = str(os.getpid())
            other_pids = [pid for pid in pids if pid != current_pid]
            
            if other_pids:
                log_message(f"הסקריפט כבר רץ (PIDs: {', '.join(other_pids)})")
                return None
        except subprocess.CalledProcessError:
            pass  # אין תהליכים אחרים
            
        # בדיקה אם קובץ הנעילה קיים וישן
        if os.path.exists(lock_file):
            if time.time() - os.path.getmtime(lock_file) > 300:  # 5 דקות
                os.remove(lock_file)
                log_message("נמחק קובץ נעילה ישן")
            else:
                log_message("קובץ נעילה קיים ותקף")
                return None
        
        # יצירת קובץ נעילה חדש
        lock_fd = open(lock_file, 'w')
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        
        # כתיבת PID לקובץ
        pid = str(os.getpid())
        lock_fd.write(pid)
        lock_fd.flush()
        
        log_message(f"נעילה הושגה בהצלחה (PID: {pid})")
        return lock_fd
        
    except Exception as e:
        log_message(f"שגיאה בנעילת הקובץ: {str(e)}")
        return None

def release_lock(lock_fd):
    """משחרר את הנעילה"""
    try:
        if lock_fd:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            lock_fd.close()
            # מחיקת קובץ הנעילה
            lock_file = os.path.join(BASE_DIR, 'check_updates.lock')
            if os.path.exists(lock_file):
                os.remove(lock_file)
    except Exception as e:
        log_message(f"שגיאה בשחרור הנעילה: {str(e)}")

def validate_directories():
    """בדיקת תקינות התיקיות"""
    try:
        # וידוא שהתיקיות קיימות
        for dir_path in [CONFIG_WATCH_DIR, CONFIG_PROCESSED_DIR]:
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
    # ניסיון לקבל נעילה (כולל בדיקת תהליכים כפולים)
    lock_fd = acquire_lock()
    if not lock_fd:
        return False

    try:
        if not check_permissions():
            print("שגיאה: לא ניתן להגדיר הרשאות נדרשות")
            return False
            
        # בדיקת תקינות התיקיות
        if not validate_directories():
            print("שגיאה: לא ניתן לוודא תקינות תיקיות")
            return False

        if len(sys.argv) > 1 and sys.argv[1] == "--single":
            return run_single_check()
        
        log_message("התחלת מעקב אחר שינויים...")
        
        # הגדרת מאזין לתיקיית pending
        event_handler = ConfigFileHandler()
        observer = Observer()
        observer.schedule(event_handler, CONFIG_WATCH_DIR, recursive=False)
        observer.start()
        
        last_auto_check = 0
        
        try:
            while True:
                current_time = time.time()
                
                # בדיקת עדכונים אוטומטית כל 10 דקות
                if current_time - last_auto_check >= AUTO_CHECK_INTERVAL:
                    log_message("מתחיל בדיקה תקופתית...")
                    check_processed_configs()
                    last_auto_check = current_time
                    log_message(f"הבדיקה הבאה תתבצע בעוד {AUTO_CHECK_INTERVAL/60} דקות")
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            observer.stop()
            observer.join()
            
    finally:
        release_lock(lock_fd)

if __name__ == '__main__':
    sys.exit(0 if main() else 1) 
