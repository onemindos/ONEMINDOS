# Website Patterns for OneMind OS (Part C)

Research date: 2026-11-10. Method: `curl` of each site's HTML and response headers (generator meta tags, asset paths, `server`/`powered-by` headers), Shopify `/products.json` feeds, and page fetches. "Detected" = a concrete signal observed. "Inferred" = weaker signal, flagged. Nothing was installed or executed from these sites.

## 1. What each reference company actually uses

| Site / function | Stack detected | Evidence |
|---|---|---|
| **Umbrel** marketing (umbrel.com) | **Next.js on Vercel** | `/_next/static` (300 hits), `server: Vercel` |
| Umbrel store | **Shopify** | store.umbrel.com `powered-by: Shopify`, `/products.json` with 16 SKUs (Home, Pro, "Umbrel Protect" add-ons) |
| Umbrel app store site | Next.js on Vercel | apps.umbrel.com `server: Vercel`, `_next` assets |
| Umbrel community | **Discourse** | community.umbrel.com generator meta "Discourse 2026.11.0-latest" |
| Umbrel docs | App dev docs live in GitHub (`umbrel-apps` README); docs.umbrel.com returned Vercel "DEPLOYMENT_NOT_FOUND" | so no separate docs site was live at that host |
| **Olares** marketing (www.olares.com) | Vue SPA built with Vite behind **Cloudflare** | `data-v-*` scoped-style attrs, `type=module` Vite bundle `/assets/app-*.js` (framework Vue is inferred from `data-v`) |
| Olares docs | **VitePress** | generator meta "VitePress v1.6.4" |
| Olares blog | **WordPress** (PHP 8.4) | generator meta "WordPress 7.0.8", `x-powered-by: PHP` |
| Olares store | **Shopify** | one.olares.com / shop.olares.com `powered-by: Shopify`, one product "Olares One" |
| Olares community | **Discourse** | community.olares.com generator meta |
| Olares nav (from fetch) | Products, Ecosystem (Market, Space, LarePass), Docs, Blog, Articles, Changelog, Support policies (Shipping, Refund, Warranty, Returns, ToS, Privacy), Store, Forum, Discord, GitHub, social | https://www.olares.com |
| **Home Assistant** (home-assistant.io) | **Jekyll** static site on **Cloudflare**, **Plausible** analytics | generator meta Jekyll, `server: cloudflare`, plausible script |
| HA docs | same Jekyll site (`/docs/`) | generator meta on /docs/ |
| HA developer docs | **Astro** signature | developers.home-assistant.io (redirect chain; astro strings) |
| HA company site (Nabu Casa) | **Astro v7.4.7**, S3 + CloudFront + Cloudflare | generator meta; `via` CloudFront |
| HA community | Discourse (inferred; returned 403 to curl, site HTML references Discourse) | moderate confidence |
| HA cloud subscription | Home Assistant Cloud -> renaming to **Link** Dec 2; $6.50/mo or $65/yr | https://www.nabucasa.com/link/ |
| **Start9** (start9.com) | **Angular** app (Taiga UI) served by **Express** | `ng-c*` attrs, `tui-*` CSS variables, `X-Powered-By: Express`; pages /server-one, /riscv-router, /premium-support, /reviews, /returns, /shipping, /warranty |
| Start9 community | **Discourse** | community.start9.com generator meta |
| Start9 store | Same Angular app (Server One "Configure and Buy" page); not Shopify | store.start9.com 301s to start9.com; products.json not Shopify |
| **ZimaOS / IceWhale** (zimaspace.com) | **Nuxt** on Cloudflare | `__NUXT__`, `/_nuxt/` (182 hits) |
| Zima store | **Shopify** (`shop.zimaspace.com`), includes `/blogs/zima-campaign-hub` and `/pages/affiliate-program` | `powered-by: Shopify`; 50 products in feed; utm-tagged cross-links from marketing site |
| Zima community | **Discourse** | community.zimaspace.com generator meta |
| **Framework** (frame.work) | Server-rendered app with Hotwire **Turbo** (`data-turbo*`) and fingerprinted `/assets/application-*.css` (Rails-style asset pipeline) behind Cloudflare; `via: heroku-router` in headers. Rails itself is **inferred**, not confirmed | headers + HTML |
| Framework community | **Discourse** | community.frame.work generator meta |
| Framework guides/support | guides.frame.work contains Zendesk support-link configuration (support desk = Zendesk, moderate confidence) | page source |
| **System76** (system76.com) | **BigCommerce Stencil** storefront + **HubSpot** forms/analytics, behind Cloudflare/CloudFront | `cdn11.bigcommerce.com/.../stencil/` preloads, `hsforms.net` preload, hubspot (14 hits) |
| System76 support | **Astro + Starlight** docs site on S3/CloudFront | support.system76.com generator meta "Astro v7.4.4", starlight strings |
| TrueNAS (extra) | WordPress + HubSpot | generator "WordPress 7.1.4", hsforms |
| Unraid (extra) | Craft CMS (SEOmatic generator) | meta generator |
| Coolify / Nabu Casa (extra) | Astro | `data-astro`/generator |
| Dokploy / Runtipi / Cosmos / N.O.M.A.D. (extra) | Next.js (Runtipi on GitHub Pages; N.O.M.A.D. on Vercel) | `_next/static` |
| HexOS (extra) | Nuxt | `x-powered-by: Nuxt` |
| REA (rea.tools) | Agent-discovery headers (`.well-known/ai-catalog.json`, `agent-skills/index.json`, markdown alternate) | HTTP Link headers |

### Observed patterns
- **Four-surface split is universal:** (1) marketing site, (2) docs site, (3) store, (4) Discourse community - each on a separate subdomain and often a separate platform.
- **Shopify dominates hardware stores** among small hardware vendors: Umbrel, Olares, Zima all use it; System76 uses BigCommerce; Start9 builds its own in its Angular app; Framework runs its own store app.
- **Docs:** VitePress (Olares), Starlight/Astro (System76 support, HA dev docs), Jekyll (HA main docs).
- **Marketing:** Next.js (Umbrel, Dokploy, Runtipi, N.O.M.A.D.), Nuxt (Zima, HexOS), Astro (Nabu Casa, Coolify), Jekyll (HA), Angular (Start9).
- **Community = Discourse almost everywhere** (Umbrel, Olares, Zima, Start9, Framework; HA inferred). **No reference company was found using Circle.so**; Circle for education is a differentiator rather than a copy of competitors. (I searched fetched HTML only; I did not verify Circle.so capabilities - see section 3.)
- **Affiliate programs:** only Zima's was observed (a Shopify page at `/pages/affiliate-program`, linked from the marketing site footer).
- **Support policy pages are part of the nav** (Shipping, Returns, Warranty, Refund) at Olares and Start9 - needed for hardware.
- **Analytics:** Plausible (HA, Puter, Umbrel references), Google Tag Manager (Olares, Dokploy, N.O.M.A.D., Zima Stripe present) - mixed.

## 2. Recommended stack pattern for OneMind

Goal: ship fast, low ops, open-source credibility, hardware commerce, education, and agent-readiness, without building a custom backend on day one.

| Surface | Recommendation | Why (tied to evidence above) |
|---|---|---|
| Marketing site + blog + news + partners | **Astro** (static, Cloudflare Pages or Workers), content in Markdown/MDX in Git | Astro is used by Coolify, Nabu Casa and System76's docs; ships near-zero JS, fast; Git-based content suits an OSS company and AI agents editing the site; blog/news/partners are collection pages. Next.js (Umbrel) is the alternative if you need heavy app-like interactivity, but costs more ops and a JS-heavy output |
| Docs | **Astro Starlight** in the same repo (or `docs.` subdomain) | System76 and the HA developer docs use Astro/Starlight; one toolchain with the marketing site; built-in search, i18n, versioning-friendly. VitePress (Olares) is the fallback if the team prefers Vue |
| OS download page | Static page generated from the GitHub Releases API at build time (checksums, mirrors, torrent) | Umbrel's README sends users to `/downloads`; keep it static and cacheable |
| Hardware store + cart + checkout | **Shopify** (`shop.` subdomain) with the Shopify Buy button/Storefront API optionally embedded in the Astro site | Umbrel, Olares and Zima all use Shopify; handles tax, shipping, returns, inventory, pre-orders/deposits (Olares used a deposit scheme), gift cards. Keep checkout off the marketing site |
| Affiliate links | Shopify affiliate/referral app or a dedicated affiliate page like Zima's (`/pages/affiliate-program`); UTM-tag all cross-links from the marketing site as Zima does | Observed pattern; cheap to start |
| Forms (leads, partners, press, waitlist) | **Zoho Forms** embeds or POST-to-Zoho from Astro, as the founder already plans | The reference companies mostly use HubSpot (System76, TrueNAS); Zoho is fine if Zoho CRM/Mail is already in use (the founder's environment includes Zoho tools). Embed via iframe or a Cloudflare Worker proxy to avoid layout shift. Zoho Forms feature details not verified in this research |
| Support desk | Start with **Zoho Desk** or a shared mailbox + public docs; upgrade later | Framework uses Zendesk (moderate confidence); not necessary at start. Pick the desk in the same suite as the forms/CRM to avoid integration work |
| Community | **Discourse** (self-hosted or hosted) at `community.` | Used by Umbrel, Olares, Zima, Start9, Framework (and HA, inferred); gives SSO options, searchable Q&A that agents can read |
| Education | **Circle.so** (`learn.` subdomain) as planned | No competitor was found using it, so this is differentiation. Verify custom domain, SSO and paywall/membership options before committing (**UNVERIFIED**; not researched here). Cross-link from docs and the OS UI |
| Changelog / status | Markdown changelog in the docs repo; a public status page | Olares has /changelog; HA has release-notes blog |
| Analytics | **Plausible** (or self-hosted Umami) | Privacy-aligned with a sovereignty brand; HA and Puter use Plausible |
| Hosting/CDN | **Cloudflare** in front of everything | Olares, HA, Zima, Nabu Casa, Unraid, N.O.M.A.D.-adjacent sites use Cloudflare; consistent with the rest of the DNS/edge stack |
| Agent-readiness | Publish `/.well-known/ai-catalog.json`, `agent-skills/index.json`, and a markdown (`index.md`) alternate for every page, plus `llms.txt` | REA's site does this via HTTP Link headers; fits OneMind's "AI-agent-native" claim. Formats beyond what REA's headers show were not verified |

### Proposed repo and domain layout
- Apex domain (founder owns onemindos.dev per CloudTAK config memory; final choice TBD): Astro marketing + blog + news + partners + download.
- `docs.`: Starlight. `shop.`: Shopify. `community.`: Discourse. `learn.`: Circle.so. `status.`: status page. `support.`: help desk.
- Single Git monorepo for marketing + docs; content PRs reviewed by humans/agents; CI deploys to Cloudflare.

### What to avoid
- Building a custom store (Start9 and Framework did; expensive for a young company).
- A single monolithic Next.js app for everything (Umbrel can afford it; OneMind needs agility).
- Heavy marketing JS (Umbrel's homepage HTML is ~610 KB; Olares ~100 KB; Astro-based Nabu Casa ~46 KB measured by curl size) - page weight affects SEO and low-bandwidth/edge users, which matters for a field/offline audience.

## 3. Open questions (not verified)
- Circle.so SSO, custom domain, paywall and API capabilities.
- Zoho Forms/Desk capability and pricing versus HubSpot/Zendesk.
- Whether any competitor runs a formal affiliate network beyond Zima's page.
- Exact CMS behind Framework's marketing site (Rails is inferred only).
- Olares marketing framework is inferred as Vue from `data-v` attributes.

## Sources
- https://umbrel.com (HTML/headers), https://store.umbrel.com/products.json, https://community.umbrel.com, https://apps.umbrel.com
- https://www.olares.com, https://www.olares.com/docs, https://www.olares.com/blog, https://one.olares.com/products.json, https://community.olares.com
- https://www.home-assistant.io, https://www.home-assistant.io/docs/, https://developers.home-assistant.io, https://www.nabucasa.com, https://www.nabucasa.com/link/
- https://start9.com, https://start9.com/server-one, https://community.start9.com
- https://www.zimaspace.com, https://shop.zimaspace.com/products.json, https://community.zimaspace.com
- https://frame.work, https://community.frame.work, https://guides.frame.work
- https://system76.com, https://support.system76.com
- https://www.truenas.com, https://unraid.net, https://coolify.io, https://dokploy.com, https://runtipi.io, https://cosmos-cloud.io, https://hexos.com, https://projectnomad.us, https://rea.tools
- All fetched with curl/WebFetch on 2026-11-10; signals read from generator meta tags, asset paths, and response headers.
