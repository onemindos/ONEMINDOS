# Sources: TD-tier-c-alt (Tier C teardowns: Puter, Sandstorm, FreedomBox, ClawBox and other AI boxes)

**Accessed:** 2026-11-11 · **Claims:** `evidence/claims/TD-tier-c-alt.csv` (C-TD-tier-c-alt-001…054) · **Saved copies:** `evidence/sources/TD-tier-c-alt/` with `SHA256SUMS` (text extracted from HTML; credential-like strings, emails, private IPs and a company registration number masked before saving). Wayback save requests are denied in this environment; code is pinned to git commits, which is a stronger archive than a page snapshot.

## Code (shallow clones in `<lab-dir>/src/`, pinned)

| Repo | Commit | Tag / date | Type | Used for |
|---|---|---|---|---|
| github.com/HeyPuter/puter | `44bf99f80840a145ecb515668d5bcef393bdd524` | release 26.11 line · commit 2026-11-10 | PRIMARY (code, AGPL-3.0-only) | C-…-001…010, 013, 014 |
| github.com/sandstorm-io/sandstorm | `5c7c29c16f45b64bc059ace80e896f313c590bd2` | v0.310 · 2026-10-12 | PRIMARY (code, Apache-2.0) | C-…-015…024, 028 |
| github.com/sandstorm-io/sandstorm (`master`) | `a97cf3ee19d3bf2761cd597583ca5d998de425d8` | 2026-05-25 | PRIMARY | C-…-021 (v0.308 date; `master` lags the v0.309/v0.310 tags) |
| salsa.debian.org/freedombox-team/freedombox | `fadba12ed288d0186b858dc79001811c5963cf8e` | 26.15 · 2026-11-02 | PRIMARY (code, AGPL-3.0-or-later) | C-…-029, 031…037, 041 |
| github.com/openclaw/openclaw (LICENSE only) | `926ce0a6f6f5480dc0b29d113d1e2a264691e8d3` | 2026-11-11 | PRIMARY | C-…-049 |
| github.com/NousResearch/hermes-agent (LICENSE only) | `9373dc1e315a68446f9767afd7acd15d4c0642b8` | 2026-11-11 | PRIMARY | C-…-050 |

Files read: Puter `package.json`, `LICENSE.txt`, `README.md`, `TRADEMARK.md`, `docker-compose.yml`, `install.sh` (header), `doc/{architecture,self-hosting}.md`, `src/docs/src/{user-pays-model,Apps}.md`, `src/mcp-connector/README.md`, `src/backend/drivers/ai-chat/providers/` (listing). Sandstorm `LICENSE`, `CHANGELOG.md`, `install.sh` (L467-476, L549-570), `src/sandstorm/{run-bundle.c++ (L3008-3114, L3202-3230), spk.c++, package.capnp, supervisor.c++, powerbox.capnp, backup.c++}`. FreedomBox `COPYING.md`, `debian/changelog`, `freedombox/modules/{upgrades,snapshot,backups,homeassistant,nextcloud,kiwix}/`.

Code search (C-…-054): case-insensitive keyword search of the three pinned trees for `rclpy|ros2|mavlink|zigbee|z-wave|modbus|mosquitto|opc ua`, excluding lockfiles, translations and `node_modules`; only FreedomBox's Home Assistant module and manual pages matched.

## GitHub API metadata (PRIMARY-METADATA)

| Query | Result | Claim |
|---|---|---|
| `repos/HeyPuter/puter`, `/releases`, `/contributors` | 44,143 stars; created 2024-03-03; releases 26.10, 26.10.1, 26.11 | C-…-012 |
| `repos/sandstorm-io/sandstorm`, `/tags` | 7,082 stars; pushed 2026-11-01; tags v0.308…v0.310 | C-…-027 |
| `repos/openclaw/openclaw`, `repos/NousResearch/hermes-agent` | MIT; ~394k and ~262k stars | C-…-049, 050 |

## Web pages

| # | URL | Type | Saved copy | Claims |
|---|---|---|---|---|
| 1 | https://puter.com/ (pricing section) | PRIMARY | `puter-root.txt` | 011 |
| 2 | https://sandstorm.org/ | PRIMARY | `sandstorm-org.txt` | 023, 026 |
| 3 | https://sandstorm.io/ | PRIMARY | `sandstorm-io.txt` | 026 |
| 4 | https://sandstorm.io/news/2019-09-15-shutting-down-oasis | PRIMARY | `sandstorm-oasis.txt` | 025 |
| 5 | https://freedombox.org/ | PRIMARY | `fbx-root.txt` | 030 |
| 6 | https://freedombox.org/download/ | PRIMARY | `fbx-download.txt` | 038 |
| 7 | https://freedombox.org/download/pioneer/ | PRIMARY | `fbx-pioneer.txt` | 039 |
| 8 | https://freedombox.org/buy/ | PRIMARY | `fbx-buy.txt` | 040 |
| 9 | https://clawbox.com/home-ai-server | PRIMARY (vendor marketing) | `clawbox-home.txt` | 045, 048 |
| 10 | https://clawbox.com/hermes | PRIMARY (vendor marketing) | `cb-hermes.txt` | 042, 045 |
| 11 | https://clawbox.com/blog/2026-05-28-openclaw-hardware-requirements-2026-the-complete-guide | PRIMARY (vendor blog) | `clawbox-hwreq.txt` | 042 |
| 12 | https://clawbox.com/faq | PRIMARY (vendor) | `cb-faq.txt` | 044, 046 |
| 13 | https://clawbox.com/clawbox-price | PRIMARY (vendor) | `cb-clawbox-price.txt` | 044 |
| 14 | https://clawbox.com/clawbox-workstation | PRIMARY (vendor marketing) | `cb-clawbox-workstation.txt` | 047 |
| 15 | https://clawbox.com/terms | PRIMARY (legal terms) | `cb-terms.txt` (registration number and street masked) | 046 |
| 16 | https://ubuntu.com/about/release-cycle | PRIMARY | `ubuntu-release-cycle.txt` | 043 |
| 17 | https://www.tomshardware.com/tech-industry/artificial-intelligence/setting-up-openclaw-isnt-as-straightforward-as-the-internet-wants-you-to-think-running-local-ai-on-humble-hardware | SECONDARY (press, 2026-07-31) | `toms-openclaw.txt` | 051 |
| 18 | https://acemagic.com/blogs/about-ace-mini-pc/best-mini-pc-for-openclaw | PRIMARY (vendor blog) | `acemagic-openclaw.txt` | 052 |
| 19 | https://snyk.io/articles/clawdhub-malicious-campaign-ai-agent-skills/ | SECONDARY (security vendor research) | `snyk-clawdhub.txt` | 053 |

## Reused claims from other ledgers (not re-verified here)

C-W10-024 (ClawBox spec), C-W10-027 (Jetson dev kits not for production), C-W10-031/032 (DGX Spark), C-W16-050 (Sandstorm business post-mortem), C-TD-olares-045/046 (Olares One), C-TD-umbrelos-046/047 (Umbrel boxes), C-TD-casaos-zimaos-039 (ZimaOS Blue agent runtime).

## Looked at, not cited

Search results reporting hundreds to 1,100+ malicious ClawHub skills (Koi Security, Unit 42, eSecurity Planet, InsiderLLM) and a CVE number attributed to ClawHub: not opened at the primary source, so not used. ClawBox review aggregator gists and third-party "reviews" with conflicting prices (EUR 399/549/749): not used; the vendor's own FAQ is cited instead.
