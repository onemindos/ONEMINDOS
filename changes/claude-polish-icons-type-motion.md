---
pr: pending
branch: claude/polish-icons-type-motion
---
Colour-independent desktop polish: Inter is now self-hosted as one 35 KB subsetted woff2 in the design system (OFL licence file included, no font CDN call) and leads the font stack with the system font as fallback; clocks, counts, metrics and table cells use tabular numerals; every window, scrim, menu, dock and Launchpad animation reads the motion tokens instead of hard-coded milliseconds, so reduced motion zeroes them in one place; the Coming soon page stays reachable by path but no longer appears as a dock, Launchpad or sidebar tile; the demo catalog gives each app its own original icon instead of a monogram. Colour tokens are untouched.
