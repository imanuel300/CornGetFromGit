# מערכת עדכון אוטומטית מ-GitHub

מערכת זו מאפשרת עדכון אוטומטי של קבצי פרויקט מ-GitHub לשרת Linux. המערכת בודקת באופן תקופתי אם יש עדכונים חדשים במאגר, ואם כן - מורידה ומתקינה אותם.

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

    sudo cp check_updates.py /var/www/html/CornGetFromGit/
    sudo cp update_checker.service /etc/systemd/system/

### 4. הגדרת הרשאות

    sudo chown www-data:www-data /var/www/html/CornGetFromGit/check_updates.py
    sudo chmod 755 /var/www/html/CornGetFromGit/check_updates.py

### 5. הפעלת השירות

    sudo systemctl daemon-reload
    sudo systemctl enable update_checker
    sudo systemctl start update_checker

## הגדרות

יש לעדכן את הפרמטרים הבאים בקובץ `check_updates.py`:

    REPO_OWNER = "imanuel300"        # שם המשתמש או הארגון בגיטהאב
    REPO_NAME = "demo-project"      # שם המאגר
    DEPLOY_PATH = "/var/www/demo-project"  # נתיב התיקייה בה יותקנו הקבצים
    CHECK_INTERVAL = 300            # תדירות הבדיקה בשניות (300 = 5 דקות)

### הגדרות למאגר פרטי

אם המאגר הוא פרטי, יש ליצור Personal Access Token ב-GitHub:
1. לך ל-Settings -> Developer settings -> Personal access tokens
2. צור token חדש עם הרשאות `repo`
3. העתק את ה-token והוסף אותו לקובץ:

    GITHUB_TOKEN = "your-github-token"  # הכנס כאן את ה-token שיצרת

## בדיקת סטטוס

לבדיקת סטטוס השירות:

    sudo systemctl status update_checker

לצפייה בלוגים:

    sudo journalctl -u update_checker -f

## פתרון בעיות

1. אם השירות לא מתחיל:
   - בדוק הרשאות בתיקיות
   - וודא שכל החבילות מותקנות
   - בדוק את הלוגים עם הפקודה `journalctl`

2. אם העדכונים לא מתקבלים:
   - בדוק את הגדרות המאגר ב-GitHub
   - וודא שיש גישה לאינטרנט
   - בדוק שהנתיבים נכונים

## אבטחה

- הקוד רץ תחת משתמש www-data
- אין צורך בפתיחת פורטים
- הקוד משתמש ב-API הציבורי של GitHub
- מומלץ להגביל הרשאות בתיקיית היעד

## תמיכה

במקרה של בעיות או שאלות, ניתן:
1. לבדוק את הלוגים של המערכת
2. לבדוק את קובץ ה-state (`last_commit.json`)
3. להריץ את הסקריפט באופן ידני לבדיקה 