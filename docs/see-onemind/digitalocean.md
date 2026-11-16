<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind on a DigitalOcean droplet

This guide points at the kit that has the exact steps and the pass/fail table: **[lab-kits/LT-DO-01](../../lab-kits/LT-DO-01/README.md)**. Read its "Before you create the droplet" part first: **a droplet is on the public internet from its first second**, and OneMind's gateway speaks plain HTTP until you add HTTPS, so the Cloud Firewall comes before the droplet.

**Download** from the newest `dev-*` pre-release: `onemind-vm-do-<version>.qcow2` (a DEV BUILD, throwaway keys). **UNVERIFIED:** no one has run it on DigitalOcean yet; that is what the kit is for.
