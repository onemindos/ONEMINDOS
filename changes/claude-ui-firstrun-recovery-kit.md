---
pr: pending
branch: claude/ui-firstrun-recovery-kit
---
The first-run wizard is now driven by the gateway instead of a browser flag. A new owner-only read, GET /v1/onboarding/state, says whether setup is complete (settings saved and, once a backup destination exists, the emergency kit confirmed), so a reload or a second browser lands in the same place. The wizard gains a real recovery-kit step on /v1/backups/kit and its confirm: the owner key is shown once, held only in memory, never stored or logged, and confirmed by typing two groups back. Starter app installs show their read-only plan first and the request carries that plan hash, so the later approval is bound to exactly what was shown. Nothing is installed by the wizard.
An owner can no longer be locked out of the dashboard by a kit that was issued but never confirmed: the kit step now offers "I lost my copy: make a new kit" (the gateway rotates the key) and "Skip for now", which lets the wizard finish and leaves the kit to be created from Backups.
