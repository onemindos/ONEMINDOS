---
pr: pending
branch: claude/fix-ui-quality-landing
---
The Atlas colour check in the browser tests no longer fails at random in WebKit. On the CI runner WebKit paints in software, and after a theme switch the first frames of the glass surfaces (a blur over the wallpaper) take several seconds each, so the button stability check ran out of time before one frame arrived. The test now waits until the page paints at frame rate again before it checks the button; the pixel check itself is unchanged.
