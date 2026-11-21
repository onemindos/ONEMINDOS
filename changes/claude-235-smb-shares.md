---
pr: pending
branch: claude/235-smb-shares
status_rows:
  - UMB-FILES-5 | in-progress | share model, owner approval and File sharing screen landed (part 1); Samba and the host operation are part 2
---
Network shares, part 1 (FILES-SHARE-01, #235): the share model, the approval and the screen. The gateway keeps who has an SMB share of their own files and who has a Time Machine target (a size cap is required), in a new table. Turning a share on is the new files.share.create action: only an owner approves, an AI agent can never ask, and the check runs again at approval. GET /v1/shares/smb lists the shares (an owner sees all, anyone else their own) and says whether the box can share at all; POST /v1/shares/smb/{id}/stop lets an owner stop one, audited. The box has no file-sharing service yet, so the answer is available false with the reason, and a request is refused rather than filed; the new File sharing screen in the dashboard says so and offers nothing to press until the box reports the service. Samba, the root helper operation and per-person SMB passwords are the second part, designed in docs/leap/core/FILE-SHARING.md.
