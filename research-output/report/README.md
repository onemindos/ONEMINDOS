# Founder report source (F-10)

Source for [`../ONEMIND-OS-FOUNDATION-REPORT.pdf`](../ONEMIND-OS-FOUNDATION-REPORT.pdf), the standalone, visual report for the founder (RESEARCH-MISSION.md §6, contents 1–13).

| Path | What it is |
|---|---|
| `chapters/01-…15-*.md` | The chapters (Markdown). Every factual sentence cites a claim ID from `../evidence/claims/*.csv`. |
| `chapters/16-appendix-checklist.md` | **Generated** by `gen_checklist.py` from `checklist.tsv`: every topic of `context/00-CONVERSATION-RECORD.md` with a link to where it is answered. |
| `chapters/17-appendix-claims.md` | **Generated** by `gen_claims_appendix.py`: the source of every cited claim ID. The build fails if an ID does not resolve. |
| `checklist.tsv` | Topic checklist plus the key terms `verify_pdf.py` looks for in the PDF text. |
| `diagrams/*.mmd` | Mermaid sources (three are copied from `20-…` and `21-…`). |
| `charts/*.py` | matplotlib charts and the layered architecture figure; every number is copied from a cited research file (named in each script's docstring). |
| `img/` | Rendered PNGs. |
| `main.typ` | Typst layout (cover, contents, styles); includes the pandoc-generated body. |
| `build.sh` | Full build: diagrams → charts → appendices → pandoc → Typst → `verify_pdf.py`. |
| `verify_pdf.py` | Checks: every checklist topic appears, no raw diagram source, all images embedded, page count, and no host paths, private IPs, tailnet names or e-mail addresses. |

**Build:** `sh build.sh <python-with-matplotlib>` (needs pandoc ≥ 3.1, Typst ≥ 0.12, Mermaid CLI, poppler-utils).

**What this report adds:** no new facts. It synthesises `00`–`30` at foundation decision revision 4.1 and reuses their claim IDs; `../evidence/claims/REPORT.csv` is therefore header-only, as `RISK.csv` is.
