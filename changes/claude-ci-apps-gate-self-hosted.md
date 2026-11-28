---
pr: pending
branch: claude/ci-apps-gate-self-hosted
---
The apps `gate` matrix job now runs on the single-use `onemind-kvm` runners (x86, Docker) for trusted events, using the same trust expression as the image jobs, so an all-apps pull request no longer queues behind GitHub's free-plan hosted-job cap. Fork pull requests and a switched-off `KVM_RUNNER` stay on GitHub-hosted `ubuntu-24.04`. `max-parallel` is 12 on our runners and 4 on hosted ones. The optional Docker Hub login is skipped on self-hosted runners, and those jobs remove any leftover k3d cluster named `gate` before and after the run. The KVM runner policy test now lists the gate and pins that its Docker Hub login cannot run on self-hosted.
