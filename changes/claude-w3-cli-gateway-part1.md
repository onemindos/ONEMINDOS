---
pr: 1102
branch: claude/w3-cli-gateway-part1
---
The onemind CLI now covers four more settings areas through the gateway: users (list, invite, disable), backup (status, snapshots, run, verify, restore request), care (checkup) and update policy (show, set). Every backup write only files a request for an owner to approve. onemind update apply now files an OS update approval on the box by default instead of acting as root on the local machine, and the old local root path stays as a clearly labelled break-glass option (--local). Every new command takes --json.
 When the box cannot run an approved install, apply files nothing and points at --local, and backup requests retry as replays.
