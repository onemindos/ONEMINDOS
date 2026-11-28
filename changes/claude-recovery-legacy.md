---
pr: 1208
branch: claude/recovery-legacy
---
Legacy contacts and the claim process (gateway permissions design 25f, D-028). An owner can name up to five people who may get a read-only copy of the owner's Files home after the owner's death. Adding a contact queues a gateway action that the requesting owner approves with a fresh, action-bound passkey. Only then can that owner retrieve the signed invite. Removing a contact or cancelling and blocking a claim takes effect immediately from an owner session (L0). The contact's phone receives a legacy access key once, and the box keeps only a salted verifier.

A claim needs that key and a death certificate (PDF, JPEG or PNG) kept on the box for the household. The owner sets a wait of 14, 30, 60 or 90 days (30 by default). Owners, adults and contacts receive notices at the start, weekly and on the last day. The contact can read notices at `/v1/legacy/contact/notices`. After downtime, the latest due reminder is sent, including the last-day notice before a grant. Owner sign-in ends a claim immediately. Session, passkey, approver-key and personal-token use count as activity, including repeated requests within a minute. If another legacy contact or household adult can confirm, they must be a distinct person from the claimant.

A granted claim permits a file manifest and a bounded tar download for 12 months. The manifest and download stop when access ends. A contact key cannot renew its export window. After returning, the owner can approve a new contact and key. The data stays on the box. The API is under `/v1/auth/legacy` and `/v1/legacy`, with owner controls in Settings, Account and `onemind legacy contacts` and `onemind legacy claims`.
