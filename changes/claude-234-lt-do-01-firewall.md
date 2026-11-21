---
pr: pending
branch: claude/234-lt-do-01-firewall
---
LT-DO-01 kit: scripted DigitalOcean Cloud Firewall bound to a tag and created before the droplet (only SSH and 8080 from one IP; 4222, 6443, 10250 and 8472 stay closed), a droplet script that uses the hub user-data and refuses to run without the firewall, and tests. Tokens come from the environment only.
