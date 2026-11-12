# Sources: COST (lifecycle cost to 2036, DC-03)

Accessed 2026-11-11. Saved excerpts (HTML converted to text, e-mail addresses masked) are in `sources/COST/`, with hashes in `sources/COST/SHA256SUMS`. Wayback saves are not available in this environment, so the saved text with its hash is the archive.

| Claim(s) | URL | Type | Saved copy |
|---|---|---|---|
| C-COST-001 | https://ubuntu.com/pricing/pro | PRIMARY | `COST/ubuntu-pricing-pro.txt` |
| C-COST-002 | https://ubuntu.com/pricing/devices | PRIMARY | `COST/ubuntu-pricing-devices.txt` |
| C-COST-003 | https://ubuntu.com/pro/devices | PRIMARY | `COST/ubuntu-pro-devices.txt` |
| C-COST-004 | https://canonical.com/blog/ubuntu-20-04-end-standard-support-for-devices ; https://ubuntu.com/blog/ubuntu-18-04-eol-for-devices | PRIMARY | `COST/canonical-2004-devices.txt`, `COST/ubuntu-1804-eol-devices.txt` |
| C-COST-005 | https://www.freexian.com/lts/debian/ | PRIMARY | `COST/freexian-lts-sponsorship.txt` |
| C-COST-006 | https://www.freexian.com/lts/extended/ | PRIMARY | `COST/freexian-elts.txt` |
| C-COST-007 | https://www.debian.org/releases/ | PRIMARY | `COST/debian-releases.txt` |
| C-COST-008 | https://wiki.yoctoproject.org/wiki/Releases | PRIMARY | `COST/yocto-releases.txt` |
| C-COST-009 | https://www.redhat.com/en/blog/red-hat-device-edge-decision-framework | PRIMARY | `COST/redhat-rhde-decision-framework.txt` |
| C-COST-010 | https://global.channelonline.com/arlingtoncp/tech/Products/overview/M024316101 | SECONDARY (reseller) | `COST/reseller-rhde-3y-premium.txt` |
| C-COST-011 | https://www.cdw.com/product/red-hat-device-edge-standard-subscription-3-years-1-socket-up-to-32/7504915 | SECONDARY (reseller) | `COST/reseller-rhde-3y-standard.txt` |
| C-COST-012 | https://www.bls.gov/ooh/computer-and-information-technology/software-developers.htm | PRIMARY | **ARCHIVE-GAP**: opened through WebFetch; a direct download returned a bot-check page |
| C-COST-013 | https://www.dataguard.com/cyber-resilience-act/certification/ | SECONDARY | **ARCHIVE-GAP**: opened through WebFetch, not saved |
| C-COST-014 | Search-result absence (no Pro for Devices price found) | UNVERIFIED | — |

**Model:** `COST/cost-model.py` (all assumptions as code) and `COST/cost-model-output.txt`. Run it with `python3 -I cost-model.py`.

**Opened and not used:** CDW Device Edge Premium 1-year and 3-year listings (HTTP 403 to WebFetch). Their search-snippet prices ($269.99 and $667.99) are **not** cited. The Timesys Vigiles pricing page now redirects to lynx.com and was not followed, so no CVE-tooling price is cited.
