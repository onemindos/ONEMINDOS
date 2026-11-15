---
pr: 287
branch: feat/139-app-proxy
status_rows:
  - CORE-NET-8 | in-review | app proxy says when an app is stopped or starting; HTTPS open tested end to end (#139 part 1)
---
Opening an app tells the truth: a signed-in person who may open an app that is stopped, starting, being updated or failed now gets a 503 page that says so (and reloads itself while the app is changing) instead of a bare "No such app", and an app that is installed but not answering gets a 502 page naming it. Browsers get a small script-free HTML page, other clients plain text; nobody learns of an app they could not open, and signed-out requests still get 401. A new end-to-end test runs the real gateway over HTTPS with the box CA, opens an installed Market app through it the way the dashboard does, and checks that signed-out requests are refused.
