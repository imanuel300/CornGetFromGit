from flask import Flask, request
import requests
import zipfile
import os
import hmac
import hashlib

app = Flask(__name__)

# יש להחליף את הערכים הבאים
GITHUB_SECRET = "your_webhook_secret"
REPO_OWNER = "owner_name"
REPO_NAME = "repo_name"
DEPLOY_PATH = "/path/to/deployment/directory"

def verify_signature(payload_body, signature):
    if not signature:
        return False
    
    expected = hmac.new(
        GITHUB_SECRET.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(f"sha256={expected}", signature)

@app.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers.get('X-Hub-Signature-256')
    if not verify_signature(request.get_data(), signature):
        return 'Invalid signature', 403

    if request.json['ref'] != 'refs/heads/main':  # או branch אחר שתרצה לעקוב אחריו
        return 'Not main branch', 200

    # הורדת הקובץ ZIP מגיטהאב
    zip_url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/main.zip"
    response = requests.get(zip_url)
    
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
        os.system(f"rm -rf {DEPLOY_PATH}/*")
        os.system(f"mv {extracted_dir}/* {DEPLOY_PATH}/")
        
        # ניקוי קבצים זמניים
        os.remove(zip_path)
        os.system(f"rm -rf {extracted_dir}")
        
        return 'Success', 200
    
    return 'Failed to download', 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000) 