---
pr: 925
branch: claude/c12-wopi-host
---
A WOPI host in the gateway, so an office engine can open and save one file in Files without seeing any other file (issue #675). A person signed in with a session asks POST /v1/files/wopi/tokens for a token that names that person, that file and that session and expires after ten minutes. The engine then calls CheckFileInfo, GetFile, Lock, GetLock, RefreshLock, Unlock and PutFile under /v1/files/wopi/files with that token. Every call checks again that the session is still live and the Files role table still allows the path. Agents, API and SDK tokens and the static tokens file never get a token. Paths follow the Files rules (no dot-dot, no symlinks). PutFile needs the file's current lock and refuses with 409 a save over a change made elsewhere. Token issues, opens, locks and saves are audited. No engine is packaged (licence gate) and nothing is visible yet: the editor screen comes in the next slice.
