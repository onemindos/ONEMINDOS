---
pr: pending
branch: feat/242-kiosk-mode
---
UX-07 part 2: kiosk mode for the box's own screen. The owner runs `onemind kiosk enable` on the box and the monitor shows the local dashboard full screen (cage plus a browser in a private profile that is gone at stop, never holding the owner token) instead of the text screen; `disable` goes back, `status` says which. Off by default, and if the image has no cage or browser yet the kiosk service falls back to the text screen, so the monitor is never blank.
