<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind website (`site/`)

The public website: landing page, docs, blog, apps catalog and community page. Built with **Astro 7.4.11 + Starlight 0.42.10** (both MIT), pinned exactly in `package.json` and `package-lock.json`.

**Serves:** W-1, W-3, W-8 and A-6 (`docs/REQUIREMENTS.md`); REC-W13-09/10 (`research-output/14-…`). Research behind the design: [RESEARCH.md](RESEARCH.md). Forum plan: [FORUM.md](FORUM.md).

## Build
```sh
cd site
npm ci          # reproducible: exact versions from package-lock.json
npm run build   # static output in site/dist/
npm run dev     # local preview at http://localhost:4321
```
Node 22.23.4 or newer (Astro 7.4 requires it). CI: `.github/workflows/site.yml` builds on every pull request that touches `site/` or `apps/`. It does **not** deploy.

## What is where
| Path | What |
|---|---|
| `src/pages/index.astro` | Landing page: install first, then "What works today" |
| `src/content/docs/docs/` | Docs (Starlight): Start here, Concepts, Reference |
| `src/content/docs/blog/` | Blog posts (frontmatter `date`, `author`); index at `src/pages/blog/index.astro` |
| `src/pages/apps/` | Apps catalog, **generated at build time** from `../apps/*/onemind.app.yaml` and `scan.json` (`src/lib/apps.ts`) |
| `src/pages/community.astro` | Community page |
| `src/components/PageTitle.astro` | Adds the status badge (`status:` frontmatter) and blog byline |

## Rules for content
- **Honest status.** Every docs page sets `status: works-today | in-review | planned | mixed`. "Works today" means on `main`. When a pull request changes what works, it updates `src/content/docs/docs/index.md` **and** the table in `src/pages/index.astro` in the same PR.
- **The contract wins.** Reference pages summarise `sdk/contracts/poc-v0.md`; when they differ, fix the page.
- **Public repo.** No secrets, private addresses, host paths, emails or tailnet names (the hygiene gate checks).
- **Patterns, not code,** from competitors. Copied code only from MIT/BSD/Apache-2.0 sources, with a NOTICE entry. umbrelOS is PolyForm Noncommercial: never copy from it.

## Hosting (founder decision, not set up)
The build is plain static files, so any static host works. Set `SITE_URL` at build time for canonical links and the sitemap; set `BASE_PATH` if the site is served from a sub-path.

| Option | How | For | Against |
|---|---|---|---|
| **GitHub Pages** | Add a deploy job (`actions/upload-pages-artifact` + `actions/deploy-pages`, pinned in `os/versions.lock.yaml`) | Free; same place as the code; no new account | Project URL is `onemindos.github.io/ONEMINDOS/` (needs `BASE_PATH=/ONEMINDOS/`) unless a custom domain is set |
| **Cloudflare Pages** | Connect the repo, build command `cd site && npm ci && npm run build`, output `site/dist` | Free tier; preview URL per PR; fast global CDN; easy custom domain | A new third-party account with repo access |
| **Self-hosted on OneMind** (later) | A static-site app on a OneMind box | Dogfooding, like the forum (FORUM.md) | Needs public HTTPS exposure first |

Domain and analytics (research suggests self-hosted Umami, MIT) are founder decisions too.
