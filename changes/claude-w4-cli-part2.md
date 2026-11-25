---
pr: pending
branch: claude/w4-cli-part2
---
Gateway CLI, part 2: onemind sessions (list, revoke), onemind shares (SMB list, add as an approval request, stop, plus file links list and revoke), onemind tls (show, ca download with a fingerprint pin) and onemind network show. Every command calls a gateway route that already existed and takes --json; the only write that needs approval, turning a share on, files a files.share.create action and the CLI never approves it.
