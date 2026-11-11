# DC-22: refuter report on platform first or own image first (technical lens)

- **Conclusion under test (28 §8, qbank W18 Q286, 01 §4.4):** platform first inside an image-first plan. Core installs by script on plain Debian in weeks 1–4 (the dev loop), and the same layers produce the image from about week 3. ADR-001 D1 stands. In revision 2, P6 ("platform mode on existing Debian/Ubuntu") is a developer loop that becomes **unsupported after image GA**, and bring-your-own hardware means "flash our image". The stated basis is that every constraint-matched competitor that ran both paths dropped the script one.
- **Flip condition:** proven competitors that match OneMind's constraints all went platform first, and image first measurably delays the first usable release.
- **Lens:** technical. I read only the conclusion and its cited claims (C-W18-062…064, C-REF-DC-longevity-004…006, C-W3-028, C-TD-olares-042). I formed this view before reading any other refuter file.
- **Date:** 2026-11-11

## Verdict: **weakened** (the sequencing is upheld; the revision-2 sunset of P6 is not supported by the evidence)

The build order (platform layers first, the image from the same source from about week 3, the image gated on the rollback spike) holds. Nothing I found argues for delaying the image. The weak part is the generalisation behind the P6 sunset. **The largest comparable did not drop its non-image path. It dropped the two paths that modify or depend on the host OS, and kept a container path.** Home Assistant ended Core (a Python venv, 2.57%) and Supervised (a supervisor that takes over a host distro, 3.3%), but kept **Container** (17.00% of opted-in installs), and it is the stated migration path for users who want "more flexibility and control" [C-REF3-DC-technical-004, C-REF3-DC-technical-005]. In November 2026 Container is still one of the two listed installation types and still releases (2026.10.3 on 2026-10-28). It is deliberately reduced: no apps (add-ons), no out-of-the-box Thread or Z-Wave [C-REF3-DC-technical-006].

So the lesson is **not** "competitors drop everything but the image". It is: **drop any path that manages someone else's host OS, and keep a self-contained runtime path with a reduced feature set.** OneMind's P6 is a k3s install on someone's distro, which is closest to Supervised, the path HA killed. That supports a sunset of P6 *as written*. It does not support "BYO = flash our image only". A reduced, self-contained path (for example the OneMind platform as a container or VM appliance with no OS rollback and no host-level capabilities) is what the evidence shows surviving. 01 §4.4 already lists P4 VM appliances, which covers part of this. A container-only form is not covered.

## Strongest counter-argument

At a mature product, about 1 in 6 opted-in Home Assistant users chose to bring their own OS and accept a reduced feature set rather than flash an image. These are disproportionately developers, homelabbers and NAS owners, who are the people who write integrations and apps. That is the ecosystem funnel OneMind's marketplace (doc 29) depends on. Declaring every non-image path unsupported at image GA gives that funnel away. Doing so is justified by the cost of supporting host-OS-modifying installs, but that cost argument doesn't apply to a self-contained container or VM path.

## New sources (searched for abandonment and deprecations)

- **N1.** home-assistant/architecture discussion #1198 (2025-02-11). Opened. It gives the install-type shares and the Container recommendation. [C-REF3-DC-technical-004]
- **N2.** home-assistant/architecture discussion #1197 (2025-02-11, approved 2025-05-09). Opened. Core is 2.57%, users are pointed to OS or Container, and analytics are opt-in. [C-REF3-DC-technical-005]
- **N3.** Home Assistant installation page and home-assistant/docker releases. Opened, and the release list was queried on 2026-11-11. Container is still supported but reduced. [C-REF3-DC-technical-006]

## What would flip it

- **Back to upheld as written (image-only BYO):** HA announcing the deprecation of Container, or evidence that HA's Container users generate a support load out of proportion to their share (the stated reason for killing Core and Supervised).
- **To a formal flip of D1:** a first usable image that slips more than about 8 weeks past the script install because of the rollback spike (T-W3 series), while the script/container preview gathers users. The P0-8 build order already treats this as the risk.
- **Correction asked of 01 §4.4:** replace "BYO means flash our image" with "BYO means flash our image, or run the reduced OneMind container/VM appliance, which has no OS rollback and no host capabilities; P6 host-install stays developer-only."
