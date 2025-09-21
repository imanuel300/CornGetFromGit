#!/bin/bash
# הפעלת השירות
##sudo apt install gunicorn בגלל שלא רצים ב VENV

#sudo nano  /etc/systemd/system/update_checker.service
#sudo nano /etc/nginx/sites-available/update_checker.conf

sudo systemctl daemon-reload
sudo systemctl enable update_checker
sudo systemctl restart update_checker
sudo systemctl restart nginx

sudo systemctl status update_checker
sudo journalctl -u update_checker.service
echo "ההתקנה הושלמה בהצלחה" 
