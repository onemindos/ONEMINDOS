---
pr: pending
branch: claude/cli-path-check-precise
---
The cli-packages check for build machine paths no longer mistakes gateway routes for paths. Its grep matched "/v1/work/tasks" in the onemind work commands, although the binaries were already built with -trimpath and held no build folder. The new scripts/release/check-cli-paths.py fails on the exact build folders (checkout, HOME, GOROOT, GOPATH, module cache, runner temp) and on any string that starts a /home, /Users, /runner or /work path, with tests that include an untrimmed build.
