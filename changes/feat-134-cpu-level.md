---
pr: 322
branch: feat/134-cpu-level
---
OneMind now refuses to install or update an app the box's processor cannot run, before anything is downloaded, with a sentence that says why. Each node reports its x86-64 CPU level (x86-64-v1 to v4, read from /proc/cpuinfo; unknown on ARM or when the flags cannot be read) in its heartbeat. An app can declare the lowest level its images need in spec.requires.cpuLevel. The hub's level is checked when the install or update is requested and again when the owner approves it. The same check refuses an app whose images are not built for the box's architecture, which nothing checked before. What the gateway cannot tell (no hub heartbeat, or an older agent) is never treated as too low.
