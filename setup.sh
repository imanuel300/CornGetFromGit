#!/bin/bash
#sudo apt install gunicorn
#sudo apt install python3-flask #important
#sudo apt install gunicorn 
#sudo apt install watchdog 
#sudo apt install requests
#/usr/bin/gunicorn --workers 1 --threads 1 --worker-class=gthread --worker-connections=1000 --timeout 300 --graceful-timeout 300 --keep-alive 5 --bind unix:/var/www/html/CornGetFromGit/app.sock --log-level debug --max-requests 1000 --max-requests-jitter 50 app:app

# הפעלת השירות
#sudo nano  /etc/systemd/system/update_checker.service
#sudo nano /etc/nginx/sites-available/update_checker.conf

sudo systemctl daemon-reload
sudo systemctl enable update_checker
sudo systemctl restart update_checker
sudo systemctl restart nginx

sudo systemctl status update_checker
sudo journalctl -u update_checker.service
echo "ההתקנה הושלמה בהצלחה" 
