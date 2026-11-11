// OneMind OS Foundation Report: layout. Content comes from chapters/*.md via pandoc (see build.sh).
#let ink = rgb("#14213D")
#let accent = rgb("#2F5D9E")
#let gold = rgb("#C9A227")
#set document(title: "OneMind OS Foundation Report", author: "OneMind OS research run")
#set page(paper: "a4", margin: (x: 2.0cm, top: 2.2cm, bottom: 2.2cm),
  header: context { if counter(page).get().first() > 2 [
    #set text(size: 8pt, fill: luma(120)); OneMind OS Foundation Report #h(1fr) Draft for founder review · 2026-11-11 ] },
  footer: context { if counter(page).get().first() > 1 [
    #set text(size: 8pt, fill: luma(120)); #h(1fr) #counter(page).display("1") #h(1fr) ] })
#set text(font: ("Charter", "Georgia"), size: 10.2pt, fill: ink, lang: "en")
#set par(justify: true, leading: 0.62em, spacing: 0.95em)
#show raw: set text(font: "Menlo", size: 8.6pt)
#set heading(numbering: "1.1")
#show heading: set text(font: ("Inter", "Helvetica"), fill: ink)
#show heading.where(level: 1): it => {
  pagebreak(weak: true)
  block(above: 0pt, below: 1.1em, width: 100%)[
    #set text(size: 20pt, weight: "bold")
    #if it.numbering != none [#text(fill: accent)[Chapter #counter(heading).display("1")] #linebreak()]
    #it.body
    #v(2pt) #line(length: 100%, stroke: 1.2pt + gold)
  ]
}
#show heading.where(level: 2): set text(size: 13pt, weight: "bold")
#show heading.where(level: 2): set block(above: 1.4em, below: 0.7em)
#show heading.where(level: 3): set text(size: 11pt, weight: "bold")
#show link: set text(fill: accent)
#set table(stroke: 0.4pt + luma(205), inset: (x: 5pt, y: 4pt),
  fill: (x, y) => if y == 0 { rgb("#E8EEF7") } else if calc.even(y) { rgb("#FAFBFD") })
#show table: set text(size: 8.3pt, hyphenate: true)
#show table.cell: set align(left + top)
#show table: set par(justify: false, leading: 0.5em)
#show table.cell.where(y: 0): set text(weight: "bold", font: ("Inter", "Helvetica"), size: 8pt)
#show figure: set block(breakable: true)
#show figure.where(kind: table): set block(breakable: true)
#show figure.caption: set text(size: 8.5pt, style: "italic", fill: luma(80))
#show quote.where(block: true): it => block(width: 100%, fill: rgb("#FFF8E1"), inset: (x: 12pt, y: 10pt), radius: 4pt,
  stroke: (left: 3pt + gold), above: 0.6em, below: 1em)[#set text(size: 9.8pt); #it.body]

// ---------- cover ----------
#page(header: none, footer: none, margin: (x: 2.4cm, y: 2.6cm))[
  #v(3.2cm)
  #text(font: "Inter", size: 11pt, fill: accent, weight: "bold", tracking: 1.5pt)[ONEMIND OS · RESEARCH RUN F-10]
  #v(0.4cm)
  #text(font: "Inter", size: 34pt, weight: "bold")[OneMind OS \ Foundation Report]
  #v(0.3cm)
  #line(length: 40%, stroke: 2pt + gold)
  #v(0.5cm)
  #text(size: 14pt)[What OneMind OS should stand on for the next ten years, from a Raspberry Pi greenhouse to a robotics-simulation cluster, and the path to build it.]
  #v(1.6cm)
  #grid(columns: (auto, 1fr), column-gutter: 12pt, row-gutter: 8pt,
    text(weight: "bold")[Prepared for], [Zeus Delacruz, founder of OneMind OS],
    text(weight: "bold")[Date], [2026-11-11 (research run of 2026-11-10/11)],
    text(weight: "bold")[Status], [Draft for founder review. Synthesises `research-output/` files 00–30 at foundation decision revision 4.],
    text(weight: "bold")[Evidence], [Every factual sentence carries a claim ID that resolves in the research ledger; Appendix C lists each source.],
  )
  #v(1fr)
  #block(fill: rgb("#F3F6FB"), inset: 12pt, radius: 4pt, width: 100%)[
    #set text(size: 9pt)
    *The answer in one sentence.* Own a read-only image with two OS slots (RAUC) and a fresh-signal health gate, on an Ubuntu 26.04 LTS base if Canonical allows it (the locked scorecard's narrow, conditional result, with a Debian 13 version built alongside until the base is locked), k3s on every real box, NATS as the bus, one capability gateway in front of every app, device and AI agent, and ten signed plugin sockets; what each pending test result means for the base was written down in advance.
    #v(4pt)
    Not legal, tax or financial advice. Vendor prices are unpublished where stated. Lab results come from disposable virtual machines unless marked otherwise.
  ]
]

// ---------- contents ----------
#page(header: none)[
  #text(font: "Inter", size: 20pt, weight: "bold")[Contents]
  #v(0.4cm)
  #show outline.entry.where(level: 1): set text(weight: "bold")
  #outline(title: none, depth: 2, indent: 1.2em)
]

#include "body.generated.typ"
