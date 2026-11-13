---
pr: pending
branch: apps/market-unblock-2
---
Market unblock part 2: metabase, penpot and umami blocked only on their bundled Debian postgres sidecar, so they now use the Alpine postgres of the same major (18.6, 15.19, 15.19) pinned by tag and digest, running as UID 70, the same fix as paperless-ngx; the CI gate still decides their tiers. calibre-web's pin label is corrected to the tag that carries its digest. Every other blocked app keeps its tier and gets a documented hold in its README (reason, newest tag checked on 2026-11-13, what would unblock it). No gate rule, tier or licence row was touched, and Nextcloud stays on 33 (D9 pending).
