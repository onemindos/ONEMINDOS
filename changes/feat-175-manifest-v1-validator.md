---
pr: pending
branch: feat/175-manifest-v1-validator
status_rows:
  - PLAN-E6 | in-review | first slice: one validator and the v1alpha1 to v1 converter; the v1 flip of apps and the extended section 6 rules are still open
---
CI's validate-apps now runs the gateway's own manifest check (the same Catalog.validate the box uses), so the two cannot disagree. The schema and the box accept apiVersion onemind.app/v1 beside v1alpha1, and the new app-manifest tool validates manifests or converts v1alpha1 to v1 by changing only the apiVersion line.
