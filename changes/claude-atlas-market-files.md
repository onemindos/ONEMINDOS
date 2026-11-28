---
pr: 1348
branch: claude/atlas-market-files
---
Gives the desktop Market the Atlas layout (prototype 04) and the app page's waiting track (prototype 05). A sidebar lists Discover, Installed, Updates, Requests and Built in with counts from the hub, a Bring your own group (container image, Compose file, Git repository, plugin) for owners, and the sources the hub reports. Discover gains a Bring your own section with the real onemind commands, and a new Requests page lists every app request, waiting ones first. On a Market app page an install or update that waits for an owner shows five steps read from the action (requested, plan checked, approval, install, running) with Approve with passkey, Review the plan and Cancel request or Deny, all through the same gateway approval step-up as Approvals; installs that need typed secrets, a hold or licence acceptance go to Approvals instead.
