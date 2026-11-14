---
pr: pending
branch: ci/dockerhub-login
---
Optional Docker Hub login for the app-scan workflows (founder decision D18), so image pulls use the account rate limit instead of the shared runner IP. Skipped when the secret is absent and on fork pull requests. The action is pinned by commit in os/versions.lock.yaml.
