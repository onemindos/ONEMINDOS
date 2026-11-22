---
pr: pending
branch: w0/samba-firewall
---
Samba file sharing (D-017) can now be reached from the home network. The default-deny host firewall had no rule for the Windows file-sharing port 445, so shares approved on the box answered nothing. The firewall now has an empty samba chain reached from LAN, link-local and mesh source addresses only; onemind-smb.service adds the port 445 rule when it starts (it starts only while an owner has approved a share) and removes it when it stops, and restarts with the firewall so the rule is never lost. A public address never reaches 445. The firewall unit test pins this and the network-namespace port scan replays the unit's own commands to prove 445 is reachable from a LAN address, dropped from a public one, and closed while Samba is off.
