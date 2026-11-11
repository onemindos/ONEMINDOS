# kairos-io/kairos#5923: feat: faster release process
state: open created: 2026-11-03T08:58:55Z closed: null

<!-- Thanks for helping us to improve kairos! We welcome all feature requests. Please fill out each area of the template so we can better help you. Comments like this will be hidden when you post but you can delete them if you wish. -->

**Is your feature request related to a problem? Please describe.**
As with AI more CVEs are getting discovered at a faster pace, we have to start to think and adapt our release process.

- Currently, Hadron follows a non deterministic version release
- Kairos tends to have minor 1-2 release per quarter.

While this was working fine as we were more oriented on feature-releases, we need now to account as well of security releases, which are more frequent because of AI.

**Describe the solution you'd like**

Both projects (Kairos and Hadron) should release weeklies, automatically, following semver:

- Gated by green CI state
- Maintainers can bump minor releases manually to signal new features or things that deserve users attention
- Hadron should have weekly releases too
- The roadmap will become feature oriented, instead of version oriented. We will use the roadmap board for having, human-only issues, while the project board can track agents works.

**Describe alternatives you've considered**
N/A

**Additional context**
<!-- Add any other context or screenshots about the feature request here. -->

