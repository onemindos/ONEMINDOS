---
pr: 920
branch: claude/sync-pair-desktop-sensor
---
Sensor join, first slice of the desktop and small-device pairing (Refs #717): `onemind device join` takes an `onemind-join:v2` code (or a typed code with `--hub` and the required `--ca` pin), pins the box CA, shows the match code, waits for the owner's approval and writes a NATS leaf config whose local clients may publish only `onemind.node.<id>.status` and `onemind.node.<id>.event.>` and subscribe to nothing. It refuses worker and other-device codes, a hub that offers the worker role, and a hub whose CA is not the pinned one. A real nats-server test proves the sensor cannot subscribe outside its own subjects. The desktop app's join by link follows in a second PR on the same issue.
