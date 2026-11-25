---
pr: pending
branch: claude/fix-bootlock-b1-b5
---
Fixes two harness bugs that failed the boot menu lock test (B1-B6) on a correctly locked image and so blocked the T5 battery, cloud and installer jobs on release/next. B1 counted every grub.cfg line containing the word password_pbkdf2, so the image's own `insmod password_pbkdf2` (which only loads the module) read as a baked-in hash. It now counts only a line that runs the password or password_pbkdf2 command, or any grub.pbkdf2 hash, as the pre-registered criterion says. B5 waited a fixed 1.5 s after the wrong password, but GRUB sleeps before it refuses a login and doubles that sleep after each refusal (1 s for B4, 2 s for B5), so the refusal arrived after the test had looked. Each login now waits for GRUB's answer, up to the criteria's 60 s per prompt. The criteria file is unchanged and no check is loosened.
