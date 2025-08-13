
# מערכת עדכון אוטומטית מ-GitHub

מערכת זו מאפשרת עדכון אוטומטי של קבצים מ-GitHub למערכת הפעלה. המערכת תומכת בשלושה מצבי עבודה:
1. עדכון אוטומטי - בדיקת עדכונים כל 10 דקות
2. עדכון ידני - על ידי הוספת קובץ הגדרות לתיקיית `pending`
3. פריסה מחדש (Redeploy) של קובץ הגדרות קיים דרך Endpoint HTTP (ראה בהמשך)

## מבנה המערכת


```
CornGetFromGit/
├── pending/           # תיקייה לקבצי הגדרות חדשים
├── processed/         # תיקייה לקבצי הגדרות שעובדו
├── check_updates.py   # הסקריפט הראשי
├── update_process.log # קובץ לוג
└── last_commit.json   # מעקב אחר קומיטים
```

### דוגמת קריאה ל-API

```http
GET /deploy/<filename>?RUN_SETUP_SCRIPT=True&UPDATE_ONLY_CHANGED_FILES=True
```

- `<filename>` – שם קובץ ה-JSON (למשל: `auto_check.json`)
- ניתן לשלוח גם ב-GET

#### דוגמה ב-curl:
```bash
curl -X GET "http://localhost:5000/deploy/auto_check.json?RUN_SETUP_SCRIPT=True&UPDATE_ONLY_CHANGED_FILES=True"
```

- הקריאה תעביר את הקובץ מ-`processed` ל-`pending` ותעדכן את הפרמטרים בקובץ.
- המערכת תזהה את הקובץ ותבצע פריסה מחדש לפי ההגדרות החדשות.

### מימוש פנימי
ב-`check_updates.py` קיימת פונקציה בשם `redeploy_config_file` שמבצעת את ההעברה והעדכון. ניתן לייבא ולהשתמש בה גם בסקריפטים אחרים.

## קובץ הגדרות

יש ליצור קובץ JSON עם ההגדרות הבאות:

```json
{
    "repo_owner": "username",      # שם המשתמש ב-GitHub
    "repo_name": "repository",     # שם המאגר
    "deploy_path": "/path/to/dir", # נתיב התקנה
    "github_token": "",            # (אופציונלי) טוקן GitHub
    "branch": "main",             # (אופציונלי) ענף ברירת מחדל
    "setup_script": "setup.sh",    # (אופציונלי) סקריפט התקנה
    "setup_args": "production"     # (אופציונלי) פרמטרים להתקנה
}
```

## התקנה

1. העתק את הקבצים לתיקיית `/var/www/html/CornGetFromGit`
2. הרץ את סקריפט ההתקנה:
```bash
sudo chmod +x install.sh
sudo ./install.sh

# התקנת שירות
sudo cp update_checker.service /etc/systemd/system/
# טעינת שירות
sudo systemctl daemon-reload

# בדיקת הרשאות
sudo systemctl stop update_checker
sudo chown -R www-data:www-data /var/www/html/CornGetFromGit
sudo chmod -R 775 /var/www/html/CornGetFromGit
sudo systemctl start update_checker
```


## שימוש

### עדכון אוטומטי
1. צור קובץ הגדרות (לדוגמה: `auto_check.json`)
2. העתק את הקובץ לתיקיית `processed`
3. המערכת תבדוק עדכונים אוטומטית כל 10 דקות

### עדכון ידני
1. צור קובץ הגדרות (לדוגמה: `manual_deploy.json`)
2. העתק את הקובץ לתיקיית `pending`
3. המערכת תזהה את הקובץ מיד ותתחיל בתהליך העדכון

## מעקב אחר עדכונים

- הלוגים נשמרים ב-`update_process.log`
- קבצי ההגדרות המעובדים ב-`processed` מכילים היסטוריית עדכונים
- ניתן לראות את סטטוס השירות:
```bash
sudo systemctl status update_checker
```

## פקודות שימושיות

```bash
# הפעלת השירות
sudo systemctl start update_checker

# עצירת השירות
sudo systemctl stop update_checker

# הפעלה מחדש
sudo systemctl restart update_checker

# צפייה בלוגים
tail -f /var/www/html/CornGetFromGit/update_process.log

# בדיקה ידנית
sudo -u www-data /usr/bin/python3 /var/www/html/CornGetFromGit/check_updates.py --single

# בדיקת סטטוס השירות
systemctl | grep update_checker
sudo systemctl status update_checker

```

## הרשאות

המערכת רצה תחת המשתמש `www-data` ודורשת הרשאות מתאימות:
- קריאה/כתיבה לתיקיות `pending` ו-`processed`
- הרשאות הרצה לסקריפט `check_updates.py`
- הרשאות כתיבה לקובץ הלוג

## פתרון בעיות

1. בדוק את הלוגים:
```bash
tail -f /var/www/html/CornGetFromGit/update_process.log
```

2. וודא הרשאות:
```bash
ls -la /var/www/html/CornGetFromGit/
```

3. בדוק סטטוס שירות:
```bash
sudo systemctl status update_checker
```

4. אפס את המערכת:
```bash
sudo systemctl stop update_checker
sudo rm -f /var/www/html/CornGetFromGit/check_updates.lock
sudo systemctl start update_checker
```