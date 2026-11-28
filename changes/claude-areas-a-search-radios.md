---
pr: pending
branch: claude/areas-a-search-radios
---
Two gaps from the UI parity report are closed. Search: a Search screen in the dashboard and `onemind search WORDS...` over `GET /v1/search`, with results grouped by kind and linked inside the app, and a plain message when the index is still building. Radios: the Nodes page now lists every radio found on the machines and lets an owner confirm what a LoRa radio is (a human-only action, offered to owners only, with the question asked first), and `onemind radios list` and `onemind radios confirm` do the same from the command line; an agent token is refused by the gateway.
