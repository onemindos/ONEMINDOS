---
pr: pending
branch: apps/market-batch-6
---
Market batch 6: seven apps from the candidate list in score order, each non-root with no privileges, hostPath or host network, pinned by tag and digest, with probes on a real health endpoint that was checked by running the pinned image with the pod's security settings: Wiki.js (with an Alpine PostgreSQL sidecar), Jenkins, BentoPDF, MeTube, Seerr, Prometheus and Vikunja. Their tier stays community until the CI app gate computes one. Candidates that could not honestly be packaged now (privileged or root-only, or a licence the gate cannot confirm) are skipped with the reason in apps/_intake/queue.yaml.
