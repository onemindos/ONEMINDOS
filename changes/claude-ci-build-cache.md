---
pr: pending
branch: claude/ci-build-cache
---
Image builds reuse a layer cache. The image, battery and reproducible-build workflows already passed GitHub Actions cache flags to docker buildx, but a plain run step does not get the cache token, so buildx dropped them silently and every rootfs and tools build started from nothing. Each building job now exposes the token (crazy-max/ghaction-github-runtime, pinned) and builds through os/rootfs/buildx-cache.sh, which reads the cache on every run and writes it only on pushes, the nightly and manual runs, so pull requests cannot push the base branch's layers out of the 10 GB cache. Build machines can keep a local cache with make BUILDX_CACHE=<dir> for the tools, rootfs and installer builds. What gets built and tested is unchanged: the reproducible-build check still builds with no cache, and a unit test fails if a build bypasses the script, a job loses its token step or a test step disappears.
