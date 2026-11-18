---
pr: pending
branch: feat/285-path-tier
status_rows:
  - CORE-NET-8 | in-review | app exposure tier enforced by network path, not only Host (#285 follow-up)
---
The app proxy now enforces an app's exposure tier by where the request really came from, not only by the Host name it sent. A private app opens only from the home LAN, a mesh app from the LAN and the mesh, and a public app from anywhere, so a LAN-only app can no longer be reached from the internet by sending its LAN name. The path is read from the connection's own address (mesh ranges first, then private LAN, then public); a request whose path cannot be told, such as loopback with no trusted edge, is refused. A reverse proxy or Tor on the box can state the path with `X-OneMind-Path`, believed only from the networks in `ONEMIND_NET_TRUSTED_PROXIES` (default none), and the forward-auth check takes it from the edge and treats silence as unknown.
