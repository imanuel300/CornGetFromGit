#!/bin/bash
# הפעלת השירות
#sudo nano  /etc/systemd/system/update_checker.service
#sudo nano /etc/nginx/sites-available/update_checker.conf

sudo systemctl daemon-reload
sudo systemctl enable update_checker
sudo systemctl restart update_checker
sudo systemctl restart nginx

echo "ההתקנה הושלמה בהצלחה" 