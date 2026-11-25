---
pr: pending
branch: claude/139-app-open-own-url
---
Open on an installed app now goes to the app's own name behind the OneMind sign-in (for example uptime-kuma.onemind.local) instead of its raw port, which skipped the sign-in. The dashboard sets the app sign-in cookie first, and from an address that cannot name the app (an IP) it shows no link and says why. A new end-to-end test proves that every method and path on an app URL is refused when signed out, and that no request reaches the app.
