---
pr: 1160
branch: claude/refs-not-closes
---
Pull requests now link issues with "Refs #n" and never "Closes #n", as the founder decided on 2026-11-25: issues are closed by hand once the work is truly done, which is how the gate already works. The PR template and the builder rules in AGENT-QUEUE say so. No workflow or script parses closing keywords, so nothing else changes.
