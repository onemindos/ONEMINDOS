<!-- SPDX-License-Identifier: Apache-2.0 -->
# Competitor web presences: what they publish, on what, and what works

**Date:** 2026-11-12 · **Serves:** W-1 (website), W-3 (docs), W-8 (apps on the website), A-6 (community); REC-W13-09 and REC-W13-10 in [`research-output/14-family-education-community-website.md`](../research-output/14-family-education-community-website.md) §5–§6, which this page updates and extends.
**Method:** each homepage and a few key pages were fetched over HTTPS on 2026-11-12. "Stack" is read from response headers (`server`, `x-vercel-*`, `x-nf-request-id`, `x-github-*`), `<meta name="generator">` and asset paths (`/_next/`, `/_nuxt/`, `astro-`, `wp-content`). A stack that was only inferred from a URL pattern is marked **UNVERIFIED**. Section lists come from each page's own navigation links and headings. Nothing was copied: the OneMind site takes **patterns only**, and its code is our own (see "Licence notes").

> **Explain it like I'm the founder.** Every serious competitor runs a fast static or JavaScript marketing site, keeps docs in a separate static generator, and uses Discourse as the forum. The two that stand out for us are **Omarchy**, whose home page puts the install first and then proves itself with plain facts and real numbers, and **Home Assistant**, whose "My" links let a public web page open a page on *your* box without the website ever learning where your box is. No competitor shows an honest "what works today" table, and none shows a per-app trust card with scan results. Those are the two gaps the OneMind site fills.

---

## 1. Summary table

| Project | Main site stack | Docs | Forum / community | App store on the web | Install path on the homepage |
|---|---|---|---|---|---|
| **Omarchy** | Astro, behind Cloudflare | `/manual/` on the same site (older manual: Writebook, a Rails app, at learn.omacom.io) | Discord, meetups, GitHub | `plugins.omarchy.org` (separate site); themes on `/themes/` | **ISO download with signature, first thing after the hero** |
| **umbrelOS** | Next.js on Vercel | Help centre at `/support` (no docs subdomain) | Discourse (`community.umbrel.com`, Discourse 2026.11) | `apps.umbrel.com` (Next.js, Vercel), 300+ apps, category pages | `/downloads`, plus hardware product pages |
| **Home Assistant** | Jekyll on Netlify, behind Cloudflare | `/docs/` on the same site; developer docs on a separate site | Discourse (`community.home-assistant.io`, behind a Cloudflare challenge on 2026-11-12) | No web store; "My" redirect links; the 2026.11 release added an in-app Marketplace | `/installation/`: buy Green, or bring your own hardware, or container/VM |
| **CasaOS / ZimaOS** | CasaOS: WordPress (nginx). Zima: Nuxt, behind Cloudflare | `wiki.casaos.io` (path pattern suggests Wiki.js, **UNVERIFIED**); `zimaspace.com/docs/` | Discord; blog at `blog-casaos.zimaspace.com` | none found on the web | one-line `curl … \| bash` (CasaOS); hardware store (Zima) |
| **Start9 (StartOS)** | Ghost (Express) | `docs.start9.com`: a hand-written static hub linking to per-product books (engine **UNVERIFIED**) | Discourse (`community.start9.com`, Discourse 2026.11) | none on the web | hardware pages (`/server-one`) and software pages |
| **Olares** | Behind Cloudflare; Google Tag Manager | VitePress 1.6.4 at `/docs/` | `/forum` link plus Discord | `olares.com/market/` (Vue app) | "Get started → Install Olares" in docs; Olares One in a Shopify shop |
| **TrueNAS** | WordPress 7.1 (KeyCDN), HubSpot | `/docs/` hub (Hugo markers) | Discourse (`forums.truenas.com`, Discourse 2026.7) | `apps.truenas.com` | download page; enterprise sales funnel |
| **Unraid** | Craft CMS (SEOmatic generator), behind Cloudflare | Docusaurus at `docs.unraid.net` | Invision Community (`forums.unraid.net`), Discord | `unraid.net/community/apps` (Community Apps) | `/download`: USB Creator for Windows/Mac/Linux, trial licence |
| **Cosmos** | Next.js | `/docs/` on the same site | GitHub issues | `/cosmos-ui/market-listing` | Docker one-liner in docs |
| **Runtipi** | Next.js on GitHub Pages | `/docs/` with Quick start, Guides, Learn, Reference | GitHub, Discord | `/docs/apps-available` | `curl -L https://setup.runtipi.io \| bash` on Quick start |
| **YunoHost** | static (nginx) | `doc.yunohost.org` | Discourse (`forum.yunohost.org`) | `apps.yunohost.org` with categories | `doc.yunohost.org/install`; "try" demo |
| **Coolify** | Astro, behind Cloudflare | `/docs` (Set up, first app, API, CLI, **MCP**) | Discord, GitHub Discussions | `/services` (service templates) | install command; cloud sign-up |
| **balena** | Webflow, behind Cloudflare | GitBook at `docs.balena.io` | Discourse-style forum at `forums.balena.io` (engine not checked) | `hub.balena.io` | Etcher + cloud dashboard sign-up |

---

## 2. Per project

### 2.1 Omarchy: omarchy.org (the founder's favourite)
- **URLs:** https://omarchy.org/ · manual https://omarchy.org/manual/ · doctrine https://omarchy.org/doctrine/ · security https://omarchy.org/security/ · plugins https://plugins.omarchy.org/ · repo https://github.com/omacom/omarchy (MIT; `LICENSE` read at commit `36b70f1b`, 2026-11-12).
- **Stack:** Astro (asset markers), Cloudflare (`cf-ray`), Plausible analytics. Footer: "Hosting by Cloudflare, Compute by DigitalOcean". The site's own text is "All rights reserved", separate from the MIT code.
- **Homepage, in order:** a one-line release banner ("Omarchy 4.5 floats, speaks 50 languages…") → **"Get Omarchy"** and "See it in action" → a short manifesto ("We can fix everything") → creator videos → **download block**: x86 and ARM ISO each with a **Signature** link, "write the ISO to a USB stick and answer five questions", a Mac installer, try-in-a-VM links → "It runs on almost anything" (hardware, from new laptops to a 2011 ThinkPad) → plugins with star counts → "The agentic OS" (choose your agent at first boot; send a crash to your agent) → themes ("pick one and this site wears it too") → developer tools → gaming → Windows VM → news → **"Momentum by the numbers"** (pledges, 1,371,033 ISO downloads, 46,802 stars) → testimonials from X → teams → patrons → meetups → get involved (Discord, Meetups, Contribute, Donate).
- **Manual:** short task pages (`getting-started`, `dual-boot-install`, `unattended-installs`, `mac-support`, `shell-tools`, `ai`), each with real commands such as `omarchy language list`. Getting started starts with practical warnings ("Use a wired or 2.4 GHz keyboard!").
- **Doctrine:** ten short principles as H2s ("Own the machine", "Welcome the agents", "Beauty is truth").
- **Security page:** how to report, what counts as a vulnerability, what to include, responsible disclosure, credits, and where regular bugs go instead.
- **What works:** install first, with a signature next to every download. Plain, confident tone. Proof by numbers and real people instead of adjectives. A manual written as short pages you can act on. 50 languages. The theme switcher shows the product's personality on the site itself.
- **OneMind takes (pattern):** install block in the hero; a signature/checksum next to every future image download; a short doctrine (our rule: AI asks, you approve); a manual of short task pages; a security page with a clear reporting path; numbers only when they are real.

### 2.2 umbrelOS: umbrel.com
- **URLs:** https://umbrel.com/ · https://umbrel.com/umbrelos · https://apps.umbrel.com/ · https://community.umbrel.com/ · `/downloads`, `/support`, `/umbrel-home`, `/umbrel-pro`, affiliate programme at `affiliate.umbrel.com`.
- **Stack:** Next.js on Vercel (`server: Vercel`, `/_next/`); Plausible and Umami markers. App store: Next.js on Vercel. Forum: Discourse 2026.11.0.
- **umbrelOS page:** "The home cloud OS that just slaps" → highlights → mobile → "300+ apps. One click each." → use-case blocks (files, AI, Bitcoin, media, network, home) → features (backups, storage, GPU, remote access, HTTPS, 2FA, 29 languages) → "Private by design" (built in the open, local by default, sandboxed apps, "an app store anyone can audit") → pick hardware → testimonials.
- **App store:** one page per app (`/app/<id>`) with icon, description, screenshots and related apps; category pages. "Get it on umbrelOS" goes to marketing, not to the user's box (14 §6).
- **What works:** polished product photography; the app store as a growth surface (search engines index each app page); desktop and phone app links in the footer.
- **Licence:** umbrelOS is **PolyForm Noncommercial**; the app store repo has no licence (MATRIX §2.1). **Study only. Nothing from umbrel.com, its apps site or its repositories is copied.**
- **OneMind takes (pattern):** one indexable page per app, generated from the catalog; category grouping later. **We beat it on:** a trust card per app, and (planned) an "Open in OneMind" button that installs through the owner's approval on their own box.

### 2.3 Home Assistant: home-assistant.io
- **URLs:** https://www.home-assistant.io/ · `/installation/` · `/blog/` (monthly release notes, e.g. `/blog/2026/11/04/release-202611/`) · `/integrations/` · https://community.home-assistant.io/ · https://companion.home-assistant.io/ · https://status.home-assistant.io/ · https://alerts.home-assistant.io/ · store at https://store.openhomefoundation.org/.
- **Stack:** Jekyll (generator link to jekyllrb.com), Netlify (`x-nf-request-id`) behind Cloudflare; Plausible. The forum answered with a Cloudflare challenge (403) to a scripted fetch on 2026-11-12; it is Discourse per C-W13-032.
- **Installation page:** buy Green → bring your own hardware (Pi, Odroid, x86-64) → container or VM → "About installation types" → companion apps.
- **Release notes:** one long post per month, with a heading per feature and the YAML to try it. 2026.11 ("A lot in store!") introduced an in-app **Marketplace** with custom repositories and "Where your downloads come from".
- **What works:** the integrations directory (one page per integration); monthly release posts that teach as they announce; a public **alerts** site for known-bad integrations; a public **status** page; "My" links (14 §6).
- **OneMind takes (pattern):** monthly release posts that explain *why*; one page per app; a status page later; an alerts feed for blocked apps (contract §10.2 already marks them `blocked`); "Open in OneMind" links built the "My" way.

### 2.4 CasaOS and ZimaOS: casaos.zimaspace.com, zimaspace.com
- **URLs:** https://casaos.zimaspace.com/ · https://wiki.casaos.io/en/home · https://blog-casaos.zimaspace.com/ · https://www.zimaspace.com/ · `/zimaos` · `/docs/` · Discord at `zimaboard.com/discord`.
- **Stack:** CasaOS site is WordPress (`wp-content`) on nginx; Zima is Nuxt (`/_nuxt/`) behind Cloudflare, in 13 languages.
- **What works:** a one-line install for CasaOS; hardware-first Zima site with a distributor list and store policies.
- **Watch-out:** CasaOS has been close to idle on GitHub for a year (MATRIX §2.1), and the site does not say so. OneMind's "What works today" table is the antidote.

### 2.5 Start9: start9.com
- **URLs:** https://start9.com/ · `/software/startos` · `/server-one` · `/help` · https://docs.start9.com/ (StartOS, StartTunnel, StartWRT, packaging, Bitcoin guides) · https://community.start9.com/.
- **Stack:** Ghost (`ghost` markers, `X-Powered-By: Express`); docs hub is a hand-written static page linking to per-product books (engine **UNVERIFIED**); Discourse 2026.11.
- **What works:** a separate **packaging** guide for app developers on the docs hub; product split (OS, tunnel, router) is clear; warranty, returns and shipping pages for hardware.
- **OneMind takes:** a packaging guide for app authors (our [app manifest](src/content/docs/docs/reference/app-manifest.md) page is the seed).

### 2.6 Olares: olares.com
- **URLs:** https://www.olares.com/ · `/os`, `/one`, `/larepass`, `/changelog`, `/blog/`, `/articles/`, `/forum` · docs https://www.olares.com/docs/manual/overview · market https://www.olares.com/market/ · shop https://shop.olares.com/ (Shopify).
- **Stack:** Cloudflare + Google Tag Manager for the main site; docs on **VitePress 1.6.4**; market is a Vue app.
- **Docs structure:** get started (create ID, install, join, next steps) → manual by app (Files, Market, ControlHub, Desktop) → a large **help** section of troubleshooting pages (`ts-network-not-ready`, `ts-missing-apps`, `ts-vram-shortage`) → glossary.
- **What works:** a public **changelog** page; troubleshooting pages named after the symptom; a glossary.
- **OneMind takes:** symptom-named troubleshooting pages once there are real symptoms; a glossary (the repo already defines terms in each README).

### 2.7 TrueNAS: truenas.com
- **URLs:** https://www.truenas.com/ · `/docs/` · https://apps.truenas.com/ · https://forums.truenas.com/ · `/docs/softwarestatus/` · https://security.truenas.com/.
- **Stack:** WordPress 7.1.4 on KeyCDN with HubSpot; docs hub with Hugo markers; Discourse 2026.7.3.
- **What works:** a **software status** page that tells each kind of user which release to run; a separate security advisories site.
- **OneMind takes:** a per-channel "which version should I run" table once there are releases (security/stable channels, contract §10).

### 2.8 Unraid: unraid.net
- **URLs:** https://unraid.net/ · `/download` · `/getting-started` · `/community/apps` · `/blog` (announcements, guides, releases) · https://docs.unraid.net/ · https://forums.unraid.net/ · https://status.unraid.net/ · Discord, merch, affiliates.
- **Stack:** Craft CMS (SEOmatic generator) behind Cloudflare; docs on **Docusaurus**; forum on **Invision Community**.
- **What works:** download page that picks the right USB creator per OS; the Community Apps page explains moderation ("Moderated and Vetted"), "Try before you buy".
- **OneMind takes:** the "moderated and vetted" message, backed in our case by the CI gate rather than a moderator.

### 2.9 Cosmos: cosmos-cloud.io
- **URLs:** https://cosmos-cloud.io/ · `/docs/` · `/cosmos-ui/market-listing` · `/pro`.
- **Stack:** Next.js.
- **Docs:** getting started, market, apps, URLs, users, OpenID, backups, SmartShield, VPN, storage, then a **Pro features** section.
- **Licence:** Apache-2.0 **plus Commons Clause and an anti-tampering clause**, so not open source (MATRIX §2.1). Study only.
- **OneMind takes:** docs that mark paid features in their own section, when D-001's "pro" ADR exists.

### 2.10 Runtipi: runtipi.io
- **URLs:** https://runtipi.io/ · `/docs/quick-start` · `/docs/guides/*` · `/docs/learn/*` · `/docs/reference/*` · `/docs/apps-available`.
- **Stack:** Next.js served from **GitHub Pages** (`server: GitHub.com`).
- **Docs structure:** Introduction → Quick start → **Guides** (backup and restore, auto update, expose apps) → **Learn** (how it works, networking, reverse proxy) → **Reference** (architecture, CLI, config, release notes, breaking updates) → Security (server hardening).
- **What works:** Quick start is one page with `curl … | bash`, "Access the dashboard", "Install your first app", "Success!". Docs are split into how-to, explanation and reference.
- **OneMind takes:** the same split (Start here / Concepts / Reference), and a "Success!" ending on the install page.

### 2.11 YunoHost: yunohost.org
- **URLs:** https://yunohost.org/ · https://doc.yunohost.org/ (install, try, self-hosting, help) · https://apps.yunohost.org/ · https://forum.yunohost.org/ · https://status.yunohost.org/ · translations on Weblate.
- **Stack:** static site on nginx; Discourse 2026.11.
- **What works:** a **"try" demo** before you install; an apps store with clear categories; community translation.
- **OneMind takes:** the Mac compose hub is our "try before you install"; the dashboard's mock mode can become a public demo later.

### 2.12 Coolify: coolify.io
- **URLs:** https://coolify.io/ · `/docs` · `/changelog` · `/services` · comparison pages (`/compare/coolify-vs-dokploy`, Heroku/Netlify/Vercel alternatives) · https://github.com/coollabsio/coolify (Apache-2.0).
- **Stack:** Astro, behind Cloudflare.
- **Docs:** set up → first app → first database → **API, CLI, MCP** → framework guides → service templates → community (Discord, GitHub Discussions).
- **What works:** an MCP entry in the docs' first screen (agents are a first-class audience); honest comparison pages; a public changelog.
- **OneMind takes:** MCP documented next to REST in the reference ([Contract API](src/content/docs/docs/reference/contract-api.md)); comparison pages later, written from the cited matrix.

### 2.13 balena: balena.io
- **URLs:** https://www.balena.io/ · https://docs.balena.io/ · https://hub.balena.io/ · https://forums.balena.io/ · https://status.balena.io/ · `/etcher`.
- **Stack:** Webflow behind Cloudflare; docs on **GitBook**.
- **What works:** docs split into Develop / Deploy / Manage; a hub of ready apps and blocks; industry pages (energy, industrial, robotics).
- **OneMind takes:** Develop / Deploy / Manage is a good shape for the developer docs that come with the plugin ecosystem.

---

## 3. Patterns OneMind adopts, and where we go further

| Pattern | Seen at | OneMind site |
|---|---|---|
| Install in the hero, one command, then proof | Omarchy, Runtipi, CasaOS | Landing page install block; the warning about the developer install sits next to the command, not on another page |
| Signature next to every download | Omarchy | Planned for image downloads (checksum + signature page, REC-W13-09) |
| Docs split into start / concepts / reference | Runtipi, balena, Olares | Sidebar: Start here · Concepts · Reference |
| One indexable page per app | Umbrel, HA integrations, YunoHost | `/apps/<id>/`, generated from `apps/*/onemind.app.yaml` |
| Monthly release posts that teach | Home Assistant | Blog, starting with "Why OneMind" |
| MCP documented beside the API | Coolify | Contract API page has an MCP section |
| Discourse forum | Umbrel, HA, Start9, TrueNAS, YunoHost | See [FORUM.md](FORUM.md): GitHub Discussions now, Discourse on OneMind later |
| **Honest "what works today" with status per row** | nobody | Landing page and `/docs/`, one source of truth |
| **Trust card per app (licence, digest pins, scan results, scan age)** | nobody | Every app page; grey until a scan exists |
| **Status badge on every docs page** | nobody | `status:` frontmatter → badge under the title |

## 4. Licence notes
- **Astro 7.4.11** (MIT; `LICENSE` read at tag `astro@7.4.11`, commit `d68e4f63`) and **Starlight 0.42.10** (MIT; `LICENSE` read at tag `@astrojs/starlight@0.42.10`, commit `1f47e98c`) are npm dependencies, not vendored code. **yaml 2.9.1** is ISC (npm registry metadata).
- **No code, text, images or styles** were copied from any site above. The landing page is original code that follows Omarchy's *order of sections* (a pattern). Because nothing was copied, no NOTICE entry is needed; if code is ever copied from an Apache-compatible source, it gets a NOTICE entry in the same commit.
- **umbrelOS (PolyForm Noncommercial) and Cosmos (Commons Clause)** were studied only.
