<!-- SPDX-License-Identifier: Apache-2.0 -->
# Website: docs, blog, apps and forum (CORE-WEB)

**Date:** 2026-11-12 · **Status:** proposal · **Plan epic:** E17 (launch program) · **Deeper docs:** `site/` (branch `feat/website`, uncommitted); [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md) §8 "Website"; research 14 · **Serves:** W-1…W-9; core-alignment DOC-P1, DOC-P2, DOC-B1, DOC-B2; contract §9.3 (app pages).

> **Explain it like I am the founder**
> The website is a static site built from this repo: a landing page, the docs, a blog, a public app catalog with each app's scan record, and a community page.
> It uses Astro with Starlight (docs theme with built-in Pagefind search), so it needs no server and no database.
> Discussion starts on GitHub Discussions, with giscus comments on docs and blog posts; a self-hosted Discourse forum comes when the community outgrows that.

## 1. Goals and non-goals

| Goals | Non-goals (now) |
|---|---|
| Static site from `site/`: landing, docs, blog, apps catalog, community | Store and education platforms (Shopify, Circle; later, separate) |
| Docs generated where possible: CLI reference, API from `/openapi.json`, manifest from the JSON schema | Accounts or logins on the website |
| Public app pages built from `apps/*/onemind.app.yaml` + `scan.json` (scan history, licence, tier) | Analytics that track visitors (privacy-friendly counts only, later, optional) |
| Search with Pagefind (client-side, no service) | Comments that need a OneMind backend |
| GitHub Discussions + giscus now; Discourse later | Claims beyond what tests prove (plan §6: no "never bricks", "only OS", "tamper-proof") |

## 2. What exists today (`feat/website`, uncommitted)

| Piece | Where |
|---|---|
| Astro 7.4.11 + `@astrojs/starlight` 0.42.10, `yaml` 2.9.1 | `site/package.json` |
| Config: domain-agnostic (`SITE_URL`, `BASE_PATH` env), edit links to the repo | `site/astro.config.mjs` |
| Docs: what works today, install, first steps, try on a Mac; concepts (updates and rollback, apps and trust cards, backups, fabric, approvals and agents, security); reference (CLI, contract API, app manifest) | `site/src/content/docs/docs/**` |
| Blog: "why OneMind" | `site/src/content/docs/blog/` |
| Apps catalog built from the repo | `site/src/pages/apps/`, `site/src/lib/apps.ts` |
| Community page (Discussions not switched on yet) | `site/src/pages/community.astro` |

## 3. Design

### 3.1 Stack

| Layer | Choice | Why |
|---|---|---|
| Generator | Astro (MIT) | static output, content collections, islands only where needed |
| Docs theme | Starlight (MIT) | sidebar, i18n, accessible, dark mode, edit links |
| Search | Pagefind (MIT), built into Starlight | indexes at build time, runs in the browser, no service |
| Comments | giscus (MIT) on GitHub Discussions | no database; moderation in GitHub |
| Forum later | Discourse (GPL-2.0, run as a separate app, no code copied) | categories, trust levels, email; can run as a OneMind Market app (dogfood) |

### 3.2 Generated pages
```console
$ make -C site gen          # proposed target
apps     12 pages from apps/*/onemind.app.yaml + scan.json (scan history table, last 30 scans)
cli      docs/reference/cli.md from `onemind help --markdown`
api      docs/reference/api/ from core /openapi.json (one page per tag)
schema   docs/reference/app-manifest.md from sdk/schema/onemind.app.schema.json
errors   docs/errors/<code>.md stubs for every gateway error and repair id (DOC-B1)
```
Gateway error bodies and repairs link to `https://<docs host>/errors/<code>/`, so a refusal tells the user where to read more.

Reference pages show each call in every surface (curl, CLI, Python, TypeScript, Go, MCP), generated from one example file per operation:
```yaml
# site/examples/app.install.yaml (proposed)
cli: onemind app install ntfy
python: client.actions.request("app.install", app_id="ntfy")
ts: await om.actions.request({ type: "app.install", params: { app_id: "ntfy" } })
go: om.Actions.Request(ctx, onemind.Action{Type: "app.install", Params: map[string]any{"app_id": "ntfy"}})
mcp: '{"tool": "request_action", "arguments": {"type": "app.install", "app_id": "ntfy"}}'
```

### 3.3 Community path
| Stage | Trigger | Setup |
|---|---|---|
| Now | launch L1 | Enable GitHub Discussions (categories: Q&A, Ideas, Show and tell, Apps requests); giscus on docs and blog pages, lazy-loaded behind a "Load comments" button |
| Later | > ~50 active threads a week, or need for private categories, email digests | Discourse on a OneMind box (dogfood), SSO later; Discussions archived read-only with links |

### 3.4 Hosting options (founder decision F-5)

| Option | Cost | Pros | Cons |
|---|---|---|---|
| GitHub Pages | free | builds from the repo with Actions; no new account | project-site base path unless a custom domain; limited headers (no custom CSP header) |
| Cloudflare Pages | free tier | custom headers, previews per PR | another vendor in the path |
| Netlify | free tier | headers, previews | another vendor |
| Self-hosted on a OneMind box | hardware + bandwidth | dogfood, full control | home uplink and uptime; needs public ingress (DOGFOOD) |

Default: **GitHub Pages now** (domain-agnostic build already supports `BASE_PATH`), move to self-hosted once DOGFOOD gates pass.

## 4. Security model
- Static only; no secrets in the build; `SITE_URL` and `BASE_PATH` are the only inputs.
- Content-Security-Policy via meta tag (GitHub Pages) or header (other hosts): `default-src 'self'`; giscus origin allowed only on pages with comments, loaded on click.
- Third-party embeds: none by default (no fonts, trackers or video embeds).
- Scan records shown on app pages come from the same signed data the boxes read (DOC-B2), never hand-edited.
- Redaction check in CI (plan E17): no private hostnames, addresses or personal data in `site/`.

## 5. Versioning and compatibility
- Docs track `main`; versioned docs (per release) start with the first tagged OneMind release, using Starlight's versioning approach or a `/vX/` folder.
- Generated references carry the source commit and contract version in the footer.
- Astro, Starlight and Pagefind pinned to exact versions; Renovate proposes bumps.

## 6. Test plan and acceptance

| Test | Pass when |
|---|---|
| Build | `npm ci && npm run build` green in CI; `astro check` clean |
| Links | link checker: 0 broken internal links |
| Accessibility | axe on landing, a docs page, an app page: 0 serious/critical |
| Generated | Changing `apps/ntfy/scan.json` changes the ntfy page on the next build |
| Search | Pagefind returns the install page for "install" offline |
| Redaction | CI grep for private patterns finds nothing |
| Claims | Every claim on the landing page links to a passing test or doc (plan E17) |

## 7. Build steps

| Epic | Step | Effort | Depends on |
|---|---|---|---|
| CORE-WEB-1 | Commit `site/`, CI build + link check + axe, deploy to GitHub Pages | S | – |
| CORE-WEB-2 | Generated references (CLI, API, schema, errors) | M | contract OpenAPI |
| CORE-WEB-3 | Apps catalog with scan history | S | `feat/app-pipeline` |
| CORE-WEB-4 | Discussions + giscus (click-to-load) | S | founder enables Discussions |
| CORE-WEB-5 | Blog and launch posts L1/L2/L3 | S | E17 |
| CORE-WEB-6 | Self-host on OneMind + Discourse | M | DOGFOOD gates |

## 8. Who owns which files

| Branch | Files |
|---|---|
| `feat/website` (exists) | `site/**` |
| `feat/site-gen` (proposed) | `site/scripts/gen-*.mjs`, `site/examples/**`, `.github/workflows/site.yml` |
| Hotspots (serialized) | none in core; reads the contract, schema and `apps/` read-only |
