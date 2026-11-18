---
pr: pending
branch: ci/local-runner-fresh
---
CI-10 follow-up: the local runner now gets a new VM for every job, cloned from a provisioned base and deleted afterwards, with the round time logged. The loop sets LOCAL_RUNNER to on while it runs and off when it stops, runs under caffeinate, and the doc says plainly to switch it off before the Mac sleeps.
