---
pr: 1270
branch: claude/ui-my-devices
---
Settings > Account and security gains My devices on the dashboard, the same screen the phone app has: every phone, browser and app signed in as you, what each holds (sign-ins, passkeys, approver keys, push) and when it was last seen, with Lost this device to revoke all of it in one step after a confirm. The CLI gains `onemind my-devices list` and `my-devices remove` with --json. Both call the existing GET and DELETE /v1/me/devices; the gateway keeps its own rules (your own session, a fresh passkey once the box has one, never the device in use or the last owner passkey) and the screen and CLI say each refusal in plain words. UI parity report row M4.
