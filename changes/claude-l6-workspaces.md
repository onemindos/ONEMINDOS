---
pr: 905
branch: claude/l6-workspaces
---
Adds workspaces, opt-in tiling and one keyboard map to the Atlas desktop (Refs #845). Each person gets up to four workspaces with their own windows, switched from the menu bar or Alt+1 to Alt+4, with a per-window control and Alt+Shift+digit to send a window to another one; the workspace is saved with the window session. Dragging a window to the left or right screen edge snaps it to that half. Tiling (halves, thirds, quarters, main and stack) is off by default, remembered per person and never applied on a phone. Every shortcut now lives in `shell/keys/keymap.ts`, bound only through `useKeymap`: shortcuts pause while typing, never take Ctrl/⌘ W, T, N, L or Tab, and a test fails on a collision or an unlisted binding. A Keyboard shortcuts sheet opens with `?` and from Launchpad.
