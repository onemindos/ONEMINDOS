---
pr: 921
branch: claude/e-setup-root-helper
---
Security: the first-boot setup wizard's web page no longer runs as root. It now runs as a user made up when it starts, with no special rights at all, and only shows the form and checks the setup code. A small root helper does the few things that need root (writing the setup code for the box screen, and applying the owner's choice, which hands the data folders to the service users): it answers only the wizard's own process, takes three fixed requests, checks every field again and refuses everything once the box has an owner. The helper's door exists only while the wizard runs. The wizard's sandbox score drops from 8.4 to 1.2 (lower is safer). Refs #578.
