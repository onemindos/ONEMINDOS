---
pr: pending
branch: claude/visual-webkit-flake
---
Visual tests no longer catch the desktop window mid-animation in WebKit: the settle step now injects a style that switches off every animation and transition, waits for running animations to finish, and waits until the D-016 window has the same position on three frames in a row before any screenshot is taken. The base build in CI also redraws, once, any reference screenshot that failed to draw, so a screen such as the WebKit dash-market no longer ends up without a reference.
