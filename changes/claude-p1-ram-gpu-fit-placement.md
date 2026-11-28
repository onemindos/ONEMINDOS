---
pr: pending
branch: claude/p1-ram-gpu-fit-placement
status_rows:
  - CORE-FABRIC-4 | in-review | placement now pins pods to the chosen machine, enforces GPU count and card memory, keeps big apps off the hub
---
Placement is no longer only advice. A big app such as Ollama (it needs a quarter or more of the hub's memory) now lands on a worker that fits, and the install writes that choice into the app's pods: they are pinned to that machine, and an app that needs a graphics card gets the NVIDIA runtime class and a GPU limit. Apps can ask for more than one card (requires.gpuCount) and for card memory (requires.minVramMb); onemindd now reports the card count and the smallest card's memory, and a number a machine did not report is refused rather than guessed. The chosen machine is part of the plan the owner approves, so a different machine means a new approval.
