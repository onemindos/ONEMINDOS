---
pr: 262
branch: fix/230-mac-dev-loop
---
Fix the Apple Silicon developer loop (CI-05, issue #230): canonicalize only trusted safeFS test roots, retain symlink rejection, declare isolated Python unit-test dependencies, and link both agent instruction files to a single Mac development guide distinguishing native tests from Docker Desktop or Docker-inside-Lima container builds. Image assembly and release scripts still require a Linux build environment. No production restore policy or shipping OS decision changes.
