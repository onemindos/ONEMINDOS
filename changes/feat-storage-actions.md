---
pr: pending
branch: feat/storage-actions
status_rows:
  - UMB-STOR-2 | in-review | boot assembly of the data set (onemindd storage assemble) built; image patch for LUKS2 data not applied (F-61, F-62)
  - UMB-STOR-4 | in-review | journaled operation engine in onemindd storage serve built and lab-proven with power cuts; off unless the service runs
  - UMB-STOR-5 | in-review | gateway storage routes and the five storage.mirror action types built on the feature action registry; off by default (ONEMIND_STORAGE_ENABLED)
---
Storage actions: storage.mirror.create, add, replace, remove and repair as owner-approved actions whose plans name the disk by model and the last four characters of its serial, run by a journaled engine in onemindd storage serve that resumes or rolls back after a power cut, plus a boot assembly that mounts the data set in normal, degraded or recovery mode and storage health events for notifications. Destructive types (create, add, replace, remove) are approved only with the owner passkey, even where passkey approval is otherwise optional; agents can request but never approve; disk references are validated before anything is stored or sent; and no LUKS key travels through the gateway: the recovery key route is off by default until the founder decides F-61 and F-62. Everything is off unless ONEMIND_STORAGE_ENABLED is set. Docs: docs/leap/core/STORAGE-ACTIONS.md.
