---
pr: 263
branch: ci/fewer-shared-conflicts
---
Fewer merge conflicts between parallel PRs. Gateway routers now register themselves: each module in core/onemind_core/routers/ declares its ORDER and app.py finds it, so a new feature never edits app.py. The app intake queue is one file per app in apps/_intake/queue/ instead of one shared queue.yaml, and app-scaffold reads and updates that file. Generated SDK files are marked linguist-generated, with the rule to regenerate them instead of hand-merging (CI-06, issue 231).
