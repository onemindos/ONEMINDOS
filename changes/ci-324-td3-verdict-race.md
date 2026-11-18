---
pr: pending
branch: ci/324-td3-verdict-race
---
Fixes the roughly 1 in 20 battery flake where TD3 read verdict=None after a correct fallback (#324). Reproduced from the real logs of runs 43800824571 and 43800683564: the test matched the health-gate RESULT line while the serial line was still arriving, so the captured line stopped at "verdict=environ" or earlier, even though the rollback and the last-bad marker were right. The battery now waits for the end of that line before reading it; TD3 and T4v/T5v keep every original check, and a unit test feeds the line in two parts and fails without the change.
