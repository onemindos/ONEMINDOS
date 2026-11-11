#!/bin/sh
# Builds ../ONEMIND-OS-FOUNDATION-REPORT.pdf from chapters/*.md.
# Needs: pandoc ≥ 3.1, typst ≥ 0.12, mmdc (Mermaid CLI), and a Python with matplotlib for charts.
# Usage: sh build.sh [path-to-python-with-matplotlib]
set -eu
cd "$(dirname "$0")"
PY="${1:-python3}"
# 1. diagrams and charts (small PNGs in img/)
for f in diagrams/*.mmd; do
  n=$(basename "$f" .mmd)
  mmdc -i "$f" -o "img/$n.png" -c diagrams/mermaid-config.json -s 2 -b white >/dev/null
done
"$PY" charts/architecture_stack.py img/architecture.png
"$PY" charts/make_charts.py img
# 2. appendix C (fails if any cited claim ID is missing from the ledger)
python3 -I gen_checklist.py
python3 -I gen_claims_appendix.py
# 3. Markdown -> Typst body -> PDF
pandoc chapters/*.md -f markdown -t typst --columns=100000 -o body.generated.typ
typst compile --font-path /System/Library/Fonts --root . main.typ ../ONEMIND-OS-FOUNDATION-REPORT.pdf
rm -f body.generated.typ
# 4. checks
python3 -I verify_pdf.py ../ONEMIND-OS-FOUNDATION-REPORT.pdf
