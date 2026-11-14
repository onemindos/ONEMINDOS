---
pr: pending
branch: fix/photos-authz-audit
---
When the photos service refuses a caller who has no photo library (a guest, an agent or an app agent), it now writes an authz.denied audit record the same way the files, backups and notifications routes do, as the authorization contract requires. The 403 status and error envelope are unchanged. The strict-xfail PHOTOS_NO_AUDIT markers on the seven photos rows of the route authorization matrix are removed, and a unit test asserts the record on refusal.
