---
pr: pending
branch: feat/144-me-home
status_rows:
  - UMB-DESK-1 | in-review | store and routes for the Home document; the phone applies the theme (#144)
---
Each person's Home preferences (theme, wallpaper, density, layout, dock, widgets) are now kept on the hub at /v1/me/home, with an ETag and a required If-Match on a write, so the phone and the desktop match and a cleared browser loses nothing. The phone reads the theme from the hub and lets the person change it in Settings; the rest of the document is carried through untouched. The TypeScript, Go and Python SDKs are regenerated and the TypeScript client gains me.home.get and me.home.save.
