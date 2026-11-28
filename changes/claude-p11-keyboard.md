---
pr: 1161
branch: claude/p11-keyboard
---
Keyboard layout (P-11, native-features wave 2). Settings > Language and region now has a keyboard picker, and `onemind keyboard show` and `onemind keyboard set LAYOUT [VARIANT]` do the same from a terminal. A change is a request: an owner approves it (no passkey, it is not a security change), then the host service writes the layout to /data/onemind/console/keyboard, so it survives reboots and A/B updates, and loads it into the text console (tty1 to tty6, the tty2 login) and the box's own kiosk screen. The list of layouts is the one the image ships (xkb-data), and the host refuses anything outside it, puts the previous layout back if the console cannot load the new one, and checks the same names again in the gateway. New host kind set-keymap, gateway routes GET and POST /v1/system/keyboard (action type system.set_keymap), and first-boot check F23 (pre-registered in CRITERIA-FIRSTBOOT.md section 13).
