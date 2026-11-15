---
pr: 270
branch: feat/138-dashboard-lifecycle
---
Wire dashboard app lifecycle controls to gateway plan review and approval-bound requests. Installed app management reads settings and authenticated logs; stopped apps remain manageable. Install review uses the app plan route, and the compact expandable global jobs tray shows actual ledger states and executor progress rather than guessed installation stages. Image, installer, offline-bundle and Compose dashboard builds include the generated SDK source; SDK-only edits invalidate the installer build stamp. The golden-path browser flow confirms the reviewed plan before filing requests. Test fixtures stay inside tests.
