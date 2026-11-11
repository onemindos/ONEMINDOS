# DC-22 · Platform first, or own image first? — security refuter

**Lens:** security · **Refuter:** REF3 (independent; did not read other adversarial files) · **Date:** 2026-11-11
**Target conclusion** (`28-KERNEL-IMAGE-OWNERSHIP-AND-DEV-TOOLCHAIN.md` §8, `qbank/W18.md` Q286): "platform-first inside an image-first plan". In weeks 1–4 Core installs by script on plain Debian (BYO plus the dev loop). The same layers produce the Rugix image from about week 3. The image ships to users once the W3 rollback spike passes, and until then the script install is the preview channel. D1 stands.

## Strongest counter-argument

From a security view, the riskiest part of the plan is the **script-install preview channel**, and the conclusion gives it no security controls:

1. **Script-on-any-Linux appliances have a record of critical, quickly exploited bugs on hosts the vendor doesn't control.** CasaOS, which the owner's own table lists as "script first", is "a set of services you install on top of a distribution like Ubuntu or Debian". It shipped an unauthenticated dashboard bypass (CVE-2023-37265, a trusted spoofable client IP) and JWT forgery with an empty HMAC secret (CVE-2023-37266). Public exploits appeared "only 10 days after the security release" [C-REF3-DC-security-001]. A preview channel on users' own Debian hosts has no A/B rollback, no verified boot and no guaranteed update agent. Preview users who never move to the image keep running the old version.
2. **The opposite risk: the image adds a high-privilege supervisor.** Home Assistant's Supervisor auth bypass (CVE-2023-27482) affected only the OS and Supervised installs. Core and Container "have not been affected" [C-REF3-DC-security-002]. An appliance image brings a privileged host agent (for OneMind: the update and health-gate agent plus k3s), and that agent becomes the most valuable target. The same disclosure shows the remedy: the fix reached every affected user through the Supervisor's auto-update.

Together these suggest a sharper argument for image-first, not against it. The image is the only channel with a guaranteed patch path, so the script channel should be as short-lived and as closed as possible.

## Verdict: **upheld** (with conditions)

The flip condition depends on competitor sequencing and time to first release. Security adds nothing that favours platform-only, and it strengthens image-first. Conditions to write into the plan: (a) the script install is developer-only. It is never exposed beyond localhost or the tailnet by default, carries no real user data, and gets a hard end-of-support date at image GA (consistent with the ADR's "P6 developer loop"). (b) The script installs an authenticated auto-update channel from day 1, or refuses to run once it has expired. (c) The image's privileged agent (update, health gate, Supervisor-equivalent) gets its own threat model and an external review before GA.

## What would flip it

- **To weakened:** the preview channel goes to non-developer users or is exposed publicly without an update channel, or the script path stays supported after image GA.
- **To refuted (on security):** evidence that image-based appliances in this class are patched more slowly or have more critical host-agent compromises than script installs on maintained distributions, for example a CVE record across HAOS, umbrelOS and StartOS that is worse than the record for their script or Core paths.

## Sources opened (new)
- C-REF3-DC-security-001 · https://www.sonarsource.com/blog/security-vulnerabilities-in-casaos/
- C-REF3-DC-security-002 · https://www.home-assistant.io/blog/2023/03/08/supervisor-security-disclosure/
