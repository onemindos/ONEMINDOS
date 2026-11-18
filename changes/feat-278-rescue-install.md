---
pr: pending
branch: feat/278-rescue-install
---
The rescue console now starts on real hubs. deploy/install.sh installs and enables onemind-rescue.service after the box CA pair and the owner tokens exist, checks that https://127.0.0.1:7443 answers 401 without the token, and prints the rescue URL. The image ships its own unit (binary in /usr/bin, tokens and a box-CA HTTPS pair on /data) and first boot starts it on the hub role, making the pair on the way. Both units get one read-only capability so root can read files the gateway user owns; without it the console could not open the key.
