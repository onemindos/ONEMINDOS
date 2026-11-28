---
pr: 1239
branch: docs/atlas-phone-design
---
The [founder-requested Atlas phone design](https://github.com/onemindos/ONEMINDOS/issues/1225) is in `docs/design/atlas-phone/`, with renders for Home, Map, App page, Approvals and stopping a running action. The build tickets specify the implementation and checks: #1225 for Home, #1226 for Approvals and #1227 for the App page. Home and Approvals both follow the gateway's approval card. Only a card with explicit `hold: false` permits normal approval. Start each ticket on its own `feat/<issue-key>` branch and run the mobile install, typecheck and Jest through `om-remote` with Node 22 when working from the founder's Mac.
