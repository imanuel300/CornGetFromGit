import requests
import zipfile
import os
import time
import json
import urllib3

# התעלמות מאזהרות SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# הגדרות
REPO_OWNER = "imanuel300"
REPO_NAME = "TranslateDocs"
DEPLOY_PATH = "/var/www/html/TranslateDocs"
CHECK_INTERVAL = 300  # בדיקה כל 5 דקות
STATE_FILE = "last_commit.json"
GITHUB_TOKEN = ""

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
    with open(STATE_FILE, 'w') as f:
        json.dump({'last_commit': commit_sha}, f)

def load_state():
    """טוען את מזהה הקומיט האחרון"""
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)['last_commit']
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None

def deploy_latest_version():
    """מוריד ופורס את הגרסה האחרונה"""
    zip_url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/main.zip"
    headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}
    response = requests.get(zip_url, headers=headers, verify=False)
    
    if response.status_code == 200:
        # שמירת הקובץ ZIP
        zip_path = '/tmp/repo.zip'
        with open(zip_path, 'wb') as f:
            f.write(response.content)
        
        # פריסת הקבצים
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall('/tmp')
            
        # העברת הקבצים למיקום הסופי
        extracted_dir = f"/tmp/{REPO_NAME}-main"
        os.system(f"sudo /bin/rm -rf {DEPLOY_PATH}/*")
        os.system(f"sudo /bin/mv {extracted_dir}/* {DEPLOY_PATH}/")
        
        # ניקוי קבצים זמניים
        os.remove(zip_path)
        os.system(f"sudo /bin/rm -rf {extracted_dir}")
        
        # שינוי הרשאות והרצת setup.sh מהתיקייה הנכונה
        current_dir = os.getcwd()
        os.chdir(DEPLOY_PATH)
        os.system("sudo chmod +x setup.sh")
        os.system("sudo ./setup.sh production")
        os.system(f"sudo chown -R www-data:www-data {DEPLOY_PATH}")
        os.chdir(current_dir)
        
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] התקנה הושלמה בהצלחה")
        return True
    
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] שגיאה בהורדת הקבצים")
    return False

def main():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] התחלת מעקב אחר שינויים...")
    
    while True:
        try:
            current_commit = get_latest_commit()
            last_known_commit = load_state()
            
            if current_commit and current_commit != last_known_commit:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] נמצא עדכון חדש")
                if deploy_latest_version():
                    save_state(current_commit)
            else:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] אין עדכונים חדשים")
            
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] שגיאה: {str(e)}")
            time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    main() 
