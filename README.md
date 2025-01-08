# מערכת עדכון אוטומטית מ-GitHub

מערכת זו מאפשרת עדכון אוטומטי של קבצי פרויקט מ-GitHub לשרת Linux. המערכת בכולה לפעול הן כשירות רקע והן בהפעלה ידנית חד פעמית.

## דרישות מערכת
- Python 3.6 ומעלה
- pip
- systemd
- הרשאות www-data

## התקנה 

### 1. התקנת חבילות Python הנדרשות

    pip3 install requests urllib3

### 2. הגדרת תיקיות ומיקומים

    # יצירת תיקיית היעד לפרויקט אם לא קיימת
    sudo mkdir -p /var/www/html/CornGetFromGit
    sudo chown www-data:www-data /var/www/html/CornGetFromGit

### 3. העתקת קבצים

    # העתקת קבצי המערכת
    sudo cp check_updates.py /var/www/html/CornGetFromGit/
    sudo cp update_checker.service /etc/systemd/system/

    # העתקת סקריפט ההפעלה הידנית
    sudo cp check_update.sh /usr/local/bin/
    sudo chmod +x /usr/local/bin/check_update.sh

### 4. הגדרת הרשאות

    # הגדרת הרשאות לקבצי המערכת
    sudo chown www-data:www-data /var/www/html/CornGetFromGit/check_updates.py
    sudo chmod 755 /var/www/html/CornGetFromGit/check_updates.py
    
    # יצירת קובץ המצב והגדרת הרשאות
    sudo touch /var/www/html/CornGetFromGit/last_commit.json
    sudo chown www-data:www-data /var/www/html/CornGetFromGit/last_commit.json
    sudo chmod 644 /var/www/html/CornGetFromGit/last_commit.json

### 5. הפעלת השירות

    sudo systemctl daemon-reload
    sudo systemctl enable update_checker
    sudo systemctl restart update_checker

## שימוש

### הפעלה אוטומטית
השירות רץ ברקע ובודק עדכונים כל 5 דקות. ניתן לבדוק את סטטוס השירות:

    sudo systemctl status update_checker

### הפעלה ידנית
לבדיקת עדכונים באופן חד פעמי:

    check_update.sh

* הפקודה תחזיר קוד 0 אם העדכון הצליח, או 1 אם לא היו עדכונים או שהייתה שגיאה.

## הגדרות

יש לעדכן את הפרמטרים הבאים בקובץ `check_updates.py`:

    REPO_OWNER = "imanuel300"        # שם המשתמש ו הארגון בגיטהאב
    REPO_NAME = "TranslateDocs"      # שם המאגר
    DEPLOY_PATH = "/var/www/html/bedrock-translate"  # נתיב התיקייה בה יותקנו הקבצים
    CHECK_INTERVAL = 300            # תדירות הבדיקה בשניות (300 = 5 דקות)

### הגדרות למאגר פרטי
אם המאגר הוא פרטי, יש ליצור Personal Access Token ב-GitHub:
1. לך ל-Settings -> Developer settings -> Personal access tokens
2. צור token חדש עם הרשאות `repo`
3. העתק את ה-token והוסף אותו לקובץ:

    GITHUB_TOKEN = "your-github-token"  # הכנס כאן את ה-token שיצרת

## בפייה בלוגים

לצפייה בלוגים של השירות:

    sudo tail -f /var/log/update_checker.log

או דרך journalctl:

    sudo journalctl -u update_checker -f

## פתרון בעיות

1. אם השירות לא מתחיל:
   - בדוק הרשאות בתיקיות
   - וודא שכל החבילות מותקנות
   - בדוק את הלוגים

2. אם העדכונים לא מתקבלים:
   - בדוק את הגדרות המאגר ב-GitHub
   - וודא שיש גישה לאינטרנט
   - בדוק שהנתיבים נכונים

3. אם יש בעיות הרשאה:
   - וודא שהמשתמש www-data יכול להריץ את הפקודות הנדרשות
   - בדוק את הרשאות התיקיות והקבצים

## אבטחה

- הקוד רץ תחת משתמש www-data
- אין צורך בפתיחת פורטים
- הקוד משתמש ב-API הציבורי של GitHub
- מומלץ להגביל הרשאות בתיקיית היעד 