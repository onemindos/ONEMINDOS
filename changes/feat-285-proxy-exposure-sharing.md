---
pr: 339
branch: feat/285-proxy-exposure-sharing
status_rows:
  - CORE-NET-8 | in-review | app proxy honours the exposure tier and per-app sharing (#285)
---
The app proxy now follows the owner's rules. A private app no longer answers on its mesh name (it is 404 there and opens on its LAN name), while a mesh or public app opens on both. An app that is not shared with a guest is 404 on its host, exactly as it is missing from the app list, over HTTP, WebSocket and the forward-auth check. Household members can now open apps with their own session token (before, only tokens from the tokens file worked on app hosts), and forward-auth now judges the name the person used rather than the gateway's own host name.
