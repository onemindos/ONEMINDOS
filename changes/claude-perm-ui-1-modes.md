---
pr: 1271
branch: claude/perm-ui-1-modes
---
Settings, Permissions is now a page with tabs, and its first new tab is Modes: the household default and every agent and person, each with how their requests are handled (Locked, Always ask, Ask once then remember, Auto within rules, Headless), whether they follow the household default, and the owner shown as running directly with no mode. Moving toward Locked applies at once; loosening asks for the owner's passkey only when the gateway does, by running the normal passkey sign-in and sending the change once more on the fresh session. Before the owner has a passkey the page says nothing can be loosened yet. Each tab has its own address (/settings/permissions/<tab>), and notification links to a permissions tab or rule now open it instead of the Settings index.
