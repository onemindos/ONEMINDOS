---
pr: pending
branch: feat/165-model-boundary
---
Agent REST catalog policy boundary.

Part of #165. Apply manifest AI restrictions through the existing per-app visibility hook for agent REST catalog, detail, plan and appstore readers. Health/wellness metadata defaults to display-only; unknown and unsupported explicit policies fail closed. Person display and existing sharing checks are preserved.

Does not complete provider/model enforcement, agent audit/action payload boundaries, consent/local routing, the held manifest schema or app-detail SDK/UI work. Fixtures are test-only; no model calls are made.
