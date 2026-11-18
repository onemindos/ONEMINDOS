---
pr: pending
branch: fix/232-generated-status
---
Refs #232. Add a read-only JSON preview and fragment-preserving document generation from committed origin/main, ordered by first-parent landing history. Update every matching duplicate row, recount physical rows with review aliases and state qualifiers, and stamp source provenance and explicit audit limits. Generate nightly on main into the existing gate-controlled bot branch without deleting fragments, overwriting a pending bot review, or merging automatically. This is partial issue progress: inherited rows and fragment declarations still require a full acceptance audit; merging a partial feature does not establish epic completion. Feature PRs still do not edit generated documents.
