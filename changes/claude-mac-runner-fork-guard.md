---
pr: pending
branch: claude/mac-runner-fork-guard
---
The Mac runner kit now installs a fail-closed job-started hook (CI-10 follow-up, issue 299), copied from the R530 kit. The runner runs it before every job and refuses the job if the event file or repository is unknown, or if a pull request comes from a fork or a deleted fork, so a fork PR that hard-codes the Mac runner labels in its own workflow copy still cannot run there. provision.sh installs it as onemind-ci-job-started.sh and writes ACTIONS_RUNNER_HOOK_JOB_STARTED into every runner folder's .env; unit tests run the hook on fork, deleted-fork, same-repo, push and missing-environment payloads. The running Mac runner is untouched until the kit is re-provisioned.
