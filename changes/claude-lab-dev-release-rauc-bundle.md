---
pr: pending
branch: claude/lab-dev-release-rauc-bundle
---
Nightly dev pre-releases now carry the two RAUC update bundles and the public dev CA certificate from the droplet image build, so an update test (LT-DO-01 D5, the R530 lab) can run from a release instead of an expiring CI artifact that needs a GitHub login. The release notes say the bundles are signed by a throwaway CA and stay that way until the signing ceremony (#153). A build that lacks a bundle or the certificate publishes nothing.
