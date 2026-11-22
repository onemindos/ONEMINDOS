# Self-hosted font: Inter (variable, Latin subset)

- **What:** `inter-latin-wght.woff2`, Inter 4.x variable font (weight axis 100-900), cut down to
  Basic Latin, Latin-1, common punctuation, arrows and the minus sign, and to the OpenType features the
  UI uses (kerning, ligatures, tabular numerals `tnum`, case, slashed zero). About 35 KB.
- **Source:** the npm package `@fontsource-variable/inter` 5.2.8 (`files/inter-latin-wght-normal.woff2`),
  subset again with fonttools `pyftsubset`.
- **Licence:** SIL Open Font License 1.1, see `OFL.txt` (Copyright 2016 The Inter Project Authors).
  Free to use, embed and redistribute, not to be sold on its own.
- **Why self-hosted:** a hub in a home must not call a font CDN: no tracking, works offline on the LAN.
  `fonts.css` is the only place the font is loaded; nothing in the app points at a font service.
