---
pr: 261
branch: docs/codeowners-engineering
---
Engineering guide for agents. AGENTS.md (and its copy CLAUDE.md) gains a table of where each part of the code lives and the exact command CI runs to check it, the rules that keep agent code clean (generated SDK client, wired-up features, tests in the same PR, change fragments, sign-off), and a note that the docs rule and the status table agree. A new .github/CODEOWNERS requests the maintainer on every PR, per component (CI-04, issue 229).
