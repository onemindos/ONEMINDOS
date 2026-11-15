---
pr: 270
branch: feat/138-dashboard-lifecycle
---
Wire dashboard app lifecycle controls to gateway plan review and approval-bound requests. Installed app management reads settings and authenticated logs; stopped apps remain manageable. Install review uses the app plan route, and the global jobs tray shows actual ledger states and executor progress rather than guessed installation stages. Test fixtures stay inside tests.
