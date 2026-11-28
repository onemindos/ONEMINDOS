---
pr: pending
branch: claude/ci-apps-gate-self-hosted
---
The apps gate is now two jobs with the same steps: `gate` (GitHub-hosted, the optional Docker Hub login, 4 at a time) for fork pull requests and when `KVM_RUNNER` is off, and `gate-kvm` on the single-use `onemind-kvm` runners (12 at a time) for trusted events, using the same trust expression as the image jobs. `gate-kvm` mentions no secret at all, because a job that mentions one gets it delivered to its runner even when the step is skipped, so it has no Docker Hub login and pulls anonymously. It also removes any leftover k3d cluster named `gate` before and after the run. This takes an all-apps pull request past GitHub's free-plan hosted-job cap. The KVM runner policy test lists `gate-kvm`, keeps every secret check strict, and fails if the two step lists drift apart.
