---
pr: 321
branch: feat/242-local-screen
---
UX-07 part 1: a monitor plugged into a fresh box now shows how to finish setup instead of a login prompt. A small read-only service on tty1 draws the setup address, a QR code of it, the role and whether OneMind is ready (and for a running hub, the dashboard address), and never shows a token. The QR encoder is built in (checked against a real decoder), so the image needs no new package. The optional kiosk dashboard is the next part.
