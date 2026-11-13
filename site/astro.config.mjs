// SPDX-License-Identifier: Apache-2.0
// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
// Name, description and logo come from brand/brand.json via scripts/brand-sync.py.
import brand from './src/brand.generated.json' with { type: 'json' };

const REPO = 'https://github.com/onemindos/ONEMINDOS';
// Site root with one leading and one trailing slash, whether BASE_PATH is unset, '/x' or '/x/'.
const ROOT = `/${(process.env.BASE_PATH || '').replace(/^\/+|\/+$/g, '')}/`.replace(/\/\/+/g, '/');

// The production domain is a founder decision (site/README.md, "Hosting"). Until then the
// build is domain-agnostic; set SITE_URL (and BASE_PATH for a GitHub Pages project site).
export default defineConfig({
  site: process.env.SITE_URL || undefined,
  base: process.env.BASE_PATH || undefined,
  trailingSlash: 'always',
  integrations: [
    starlight({
      title: brand.name,
      description: brand.description,
      logo: { light: './src/assets/brand/onemind-mark-color.svg', dark: './src/assets/brand/onemind-mark-on-dark.svg', alt: brand.logoAlt },
      head: brand.faviconPngSizes.map((s) => ({
        tag: 'link',
        attrs: { rel: 'icon', href: `${ROOT}favicon-${s}.png`, sizes: `${s}x${s}`, type: 'image/png' },
      })),
      social: [{ icon: 'github', label: 'GitHub', href: REPO }],
      editLink: { baseUrl: `${REPO}/edit/main/site/` },
      lastUpdated: false,
      customCss: ['./src/styles/brand.generated.css', './src/styles/theme.css'],
      components: {
        PageTitle: './src/components/PageTitle.astro',
      },
      sidebar: [
        {
          label: 'Start here',
          items: [
            { label: 'What works today', slug: 'docs' },
            { label: 'Install', slug: 'docs/getting-started/install' },
            { label: 'First steps', slug: 'docs/getting-started/first-steps' },
            { label: 'Try it on a Mac', slug: 'docs/getting-started/mac' },
          ],
        },
        {
          label: 'Concepts',
          items: [
            { label: 'Approvals and agents', slug: 'docs/concepts/approvals-and-agents' },
            { label: 'Apps and trust cards', slug: 'docs/concepts/apps-and-trust-cards' },
            { label: 'Updates and rollback', slug: 'docs/concepts/updates-and-rollback' },
            { label: 'Backups', slug: 'docs/concepts/backups' },
            { label: 'Fabric (many nodes)', slug: 'docs/concepts/fabric' },
            { label: 'Security', slug: 'docs/concepts/security' },
          ],
        },
        {
          label: 'Reference',
          items: [
            { label: 'Contract API', slug: 'docs/reference/contract-api' },
            { label: 'CLI', slug: 'docs/reference/cli' },
            { label: 'App manifest', slug: 'docs/reference/app-manifest' },
          ],
        },
        {
          label: 'More',
          collapsed: true,
          items: [
            { label: 'Apps catalog', link: '/apps/' },
            { label: 'Blog', link: '/blog/' },
            { label: 'Community', link: '/community/' },
          ],
        },
      ],
    }),
  ],
});
