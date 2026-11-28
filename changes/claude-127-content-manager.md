---
pr: 398
branch: claude/127-content-manager
---
Offline content manager (NMD-02): an owner-only Offline library page and /v1/content API that pick Kiwix books by curated pack (medical, survival, education, ham radio) or by Wikipedia language and size, read sizes from the live Kiwix OPDS catalogue, show the download size before every change and refuse a change whose size moved since, file each change as an app.configure of Kiwix that waits for the owner's approval, and check for newer releases inside the maintenance window (it requests updates, never approves them). It also fixes the Kiwix mirror setting pattern, which the gateway refused because it quantified a group.
