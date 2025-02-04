#!/bin/bash

# יצירת תיקיות
sudo mkdir -p /var/www/html/CornGetFromGit/{pending,processed}

# הגדרת הרשאות לתיקיות
sudo chown -R www-data:www-data /var/www/html/CornGetFromGit
sudo chmod -R 775 /var/www/html/CornGetFromGit

# יצירת קבצי מערכת
sudo touch /var/www/html/CornGetFromGit/update_process.log
sudo touch /var/www/html/CornGetFromGit/last_commit.json
sudo touch /var/www/html/CornGetFromGit/check_updates.lock

# הגדרת הרשאות לקבצים
sudo chown www-data:www-data /var/www/html/CornGetFromGit/update_process.log
sudo chown www-data:www-data /var/www/html/CornGetFromGit/last_commit.json
sudo chown www-data:www-data /var/www/html/CornGetFromGit/check_updates.lock
sudo chmod 664 /var/www/html/CornGetFromGit/update_process.log
sudo chmod 664 /var/www/html/CornGetFromGit/last_commit.json
sudo chmod 664 /var/www/html/CornGetFromGit/check_updates.lock

# העתקת והגדרת הרשאות לסקריפט הראשי
sudo cp check_updates.py /var/www/html/CornGetFromGit/
sudo chown www-data:www-data /var/www/html/CornGetFromGit/check_updates.py
sudo chmod 755 /var/www/html/CornGetFromGit/check_updates.py

# העתקת והגדרת שירות המערכת
sudo cp update_checker.service /etc/systemd/system/
sudo chmod 644 /etc/systemd/system/update_checker.service

# הפעלת השירות
sudo systemctl daemon-reload
sudo systemctl enable update_checker
sudo systemctl start update_checker

# הוספת הרשאות sudo ספציפיות ל-www-data
echo "www-data ALL=(ALL) NOPASSWD: /bin/chown -R www-data\:www-data /var/www/html/CornGetFromGit/*" | sudo tee -a /etc/sudoers.d/www-data-updates
echo "www-data ALL=(ALL) NOPASSWD: /bin/chmod -R 775 /var/www/html/CornGetFromGit/*" | sudo tee -a /etc/sudoers.d/www-data-updates
echo "www-data ALL=(ALL) NOPASSWD: /bin/rm -rf /var/www/html/CornGetFromGit/*" | sudo tee -a /etc/sudoers.d/www-data-updates
sudo chmod 0440 /etc/sudoers.d/www-data-updates

echo "ההתקנה הושלמה בהצלחה" 