---
pr: pending
branch: claude/fix-unit-reds
---
Two unit tests failed on release/next since the CI image-tier change (#1111) turned the image.yml matrices into fromJSON(...) expressions: test_dev_release looked for the old YAML spelling of the board entries, and test_installer_updates read the matrix as a list. Both now parse the JSON the expressions really hold (every case of the battery matrix must still cover the installer target to T5). No test was weakened.
