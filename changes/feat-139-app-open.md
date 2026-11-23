---
pr: pending
branch: feat/139-app-open
---
Proves in an end-to-end HTTPS test that opening an installed app shows an honest page when its state is unknown after a restart or when the app does not answer. The app proxy, forward-auth and the signed-out refusal were already in place; this adds no new behaviour.
