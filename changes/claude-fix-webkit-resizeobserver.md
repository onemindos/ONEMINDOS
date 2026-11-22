---
pr: pending
branch: claude/fix-webkit-resizeobserver
---
Fixes a flaky "ResizeObserver loop completed with undelivered notifications" page error on WebKit: the Desktop shell now writes its menu-bar height variable in an animation frame, once per frame and only when the value changed, so the observer callback no longer changes layout in the frame it observes. The e2e rule that any page error fails the test is unchanged.
