---
pr: pending
branch: w0/test-noise
---
Removes known test noise without weakening a check. The ui and dashboard vitest configs raise the per-test timeout from 5 s to 15 s, because their userEvent suites pass on 16 CPUs but run past 5 s on busy 4-CPU machines (nothing is skipped). Every astral-sh/setup-uv step pins uv 0.13.9, the version CI ran, so a GitHub API timeout while resolving latest cannot fail a job. The browser tests settle step now makes every image eager and decodes it before a screenshot: the Market featured app icon is a lazy image that WebKit painted late on a loaded machine, which differed by 3760 pixels on 4 of 16 runs and passed on 144 of 144 after the change.
