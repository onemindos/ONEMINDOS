---
pr: pending
branch: fix-621/ci-apps
---
Four app READMEs (audiobookshelf, immich, nextcloud, paperless-ngx) had a 2026-11-21 hold paragraph placed after the notes end marker, so the generated README no longer matched the committed one and the sdk/tools unit test failed. The paragraphs now sit inside the notes block, where the generator keeps hand-written text. No wording, pin or tier changed.
