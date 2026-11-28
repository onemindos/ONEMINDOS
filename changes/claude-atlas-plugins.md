---
pr: 1346
branch: claude/atlas-plugins
---
Plugins screen (Atlas screen 10): installed plugins from GET /v1/plugins with the five defined places each one uses, paused state, and Restart and Disable and Enable and Review update as requests through the reviewed path (Approvals, D-027). `GET /v1/plugins` gains an additive `slots` field; the `onemind plugins` CLI gains `restart`, `disable`, `enable`, `update` and a PLACES view.
