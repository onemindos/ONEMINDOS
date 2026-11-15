---
pr: pending
branch: feat/141-storage-dashboard
---
Add a read-only Storage page using gateway summary and owner-only disk health through the SDK transport. Show raw data use, member capacity/allocation and SMART observations without inferring usable free space or treating missing health as healthy. Keep disabled, unavailable, permission-denied and stale data explicit. Route legacy storage settings to the page and remove only Storage from Coming soon. Disk mutations, recovery keys and passkey approvals are not added; this is one slice of issue 141.
