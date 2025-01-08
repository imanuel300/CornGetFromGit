#!/usr/bin/python3

import requests
import zipfile
import os
import time
import json
import urllib3
import sys

# התעלמות מאזהרות SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# הגדרות
REPO_OWNER = "imanuel300"
REPO_NAME = "TranslateDocs"
DEPLOY_PATH = "/var/www/html/bedrock-translate"
CHECK_INTERVAL = 300  # בדיקה כל 5 דקות
STATE_FILE = "/var/www/html/CornGetFromGit/last_commit.json"
GITHUB_TOKEN = "" 
LOG_FILE = "/var/www/html/CornGetFromGit/update_process.log"

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
        output = os.popen(command).read()
        return_code = os.system(command)
        log_message(f"הרצת פקודה: {command}", f"Return code: {return_code}\nOutput:\n{output}")
        return return_code, output
    except Exception as e:
        log_message(f"שגיאה בהרצת פקודה {command}: {str(e)}")
        return -1, str(e)

def get_latest_commit():
    """מקבל את המזהה של הקומיט האחרון"""
    api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/main"
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
        
        # שמירת המצב
        with open(STATE_FILE, 'w') as f:
            json.dump({'last_commit': commit_sha}, f)
        
        # הגדרת הרשאות לקובץ
        os.system(f"sudo -n chown www-data:www-data {STATE_FILE}")
        os.system(f"sudo -n chmod 644 {STATE_FILE}")
        
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] עודכן קובץ המצב: {commit_sha}")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] שגיאה בשמירת המצב: {str(e)}")

def load_state():
    """טוען את מזהה הקומיט האחרון"""
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)['last_commit']
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None

def deploy_latest_version():
    """מוריד ופורס את הגרסה האחרונה"""
    try:
        log_message("מתחיל תהליך התקנה...")
        
        zip_url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/main.zip"
        headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}
        response = requests.get(zip_url, headers=headers, verify=False)
        
        if response.status_code == 200:
            log_message("הורדת הקבצים הצליחה")
            
            # שמירת הקובץ ZIP
            zip_path = '/tmp/repo.zip'
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            log_message(f"קובץ ZIP נשמר ב-{zip_path}")
            
            # פריסת הקבצים
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall('/tmp')
            log_message("קבצים חולצו בהצלחה")
                
            # העברת הקבצים למיקום הסופי
            extracted_dir = f"/tmp/{REPO_NAME}-main"
            log_message(f"מעתיק קבצים ל-{DEPLOY_PATH}")
            run_command(f"sudo -n /bin/rm -rf {DEPLOY_PATH}/*")
            run_command(f"sudo -n /bin/mv {extracted_dir}/* {DEPLOY_PATH}/")
            
            # ניקוי קבצים זמניים
            os.remove(zip_path)
            run_command(f"sudo -n /bin/rm -rf {extracted_dir}")
            log_message("קבצים זמניים נוקו")
            
            # שינוי הרשאות והרצת setup.sh
            current_dir = os.getcwd()
            os.chdir(DEPLOY_PATH)
            
            log_message("מגדיר הרשאות הרצה ל-setup.sh")
            setup_code, setup_output = run_command("sudo -n chmod +x setup.sh")
            if setup_code == 0:
                log_message("הרשאות הוגדרו בהצלחה")
            else:
                log_message(f"שגיאה בהגדרת הרשאות: {setup_code}")
            
            log_message("מריץ את setup.sh")
            install_code, install_output = run_command("sudo -n ./setup.sh production")
            if install_code == 0:
                log_message("setup.sh הסתיים בהצלחה")
            else:
                log_message(f"שגיאה בהרצת setup.sh: {install_code}")
                if install_code == 256:
                    log_message("שגיאת הרשאות - הסקריפט דורש הרשאות sudo")
            
            run_command(f"sudo -n chown -R www-data:www-data {DEPLOY_PATH}")
            os.chdir(current_dir)
            
            log_message("התקנה הושלמה בהצלחה")
            return True
        
        log_message(f"שגיאה בהורדת הקבצים: {response.status_code}")
        return False
        
    except Exception as e:
        log_message(f"שגיאה בתהליך ההתקנה: {str(e)}")
        return False

def run_single_check():
    """פונקציה שמבצעת בדיקה אחת ומסתיימת"""
    try:
        current_commit = get_latest_commit()
        if not current_commit:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] לא הצלחתי לקבל את הקומיט האחרון")
            return False
            
        last_known_commit = load_state()
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] קומיט נוכחי: {current_commit}, קומיט אחרון ידוע: {last_known_commit}")
        
        if current_commit != last_known_commit:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] נמצא עדכון חדש")
            if deploy_latest_version():
                save_state(current_commit)
                return True
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] אין עדכונים חדשים")
            # עדכון הקובץ גם אם אין שינויים (למקרה שהקובץ לא קיים)
            if not last_known_commit:
                save_state(current_commit)
        return False
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] שגיאה: {str(e)}")
        return False

def main():
    # בדיקה האם הקוד הורץ במצב בדיקה חד פעמית
    if len(sys.argv) > 1 and sys.argv[1] == "--single":
        return run_single_check()
    
    # אחרת, הרץ במצב שירות מתמשך
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] התחלת מעקב אחר שינויים...")
    while True:
        try:
            if run_single_check():
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] עדכון הותקן בהצלחה")
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] שגיאה: {str(e)}")
            time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    sys.exit(0 if main() else 1) 
