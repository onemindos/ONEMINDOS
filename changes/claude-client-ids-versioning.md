---
pr: pending
branch: claude/client-ids-versioning
---
One version for the desktop and mobile apps: scripts/release/stamp-client-versions.py writes the OS release version into the desktop and mobile files, plus the Android versionCode and iOS buildNumber the stores need, and a unit test fails if the files drift apart. The release gate now runs it, so a version the stores cannot take is refused before anything is published.
