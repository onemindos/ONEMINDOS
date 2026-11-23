---
pr: 953
branch: claude/ready-passwords-builtin
---
Passwords is built in (#679): the Vaultwarden app (AGPL-3.0, unmodified, a separate program) moves to apps/_system/vaultwarden and joins the signed system apps list as a container built-in that can be switched off but never removed, keeping its vault volume when off. A new Passwords window (/passwords) shows the box's home-network and mesh address as a QR code with the Bitwarden app steps, for signed-in people only; the QR holds the address and never a token, because each vault is locked with the person's own master password. App pages now link the upstream source. Its tier stays blocked until a fixed image passes the gate, and the Bitwarden apps cannot sign in through the app proxy until it lets apps with their own sign-in through.
