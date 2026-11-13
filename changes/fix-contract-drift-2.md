---
pr: pending
branch: fix/contract-drift-2
---
Reconciles contract drift DR2-01, DR2-02 and DR2-04 after app lifecycle: documents seven existing authentication operations, adds durable nullable approval attribution without guessing historical approvers, and delivers authorized alert, inbox, app outcome, health and existing progress facts over live and replayed events. Preserves lifecycle plan binding, owner approval and retained app data, prevents private inbox audit aliases and same-cursor sibling loss, states the count-based replay limit honestly, and regenerates OpenAPI and the three SDK schemas.
