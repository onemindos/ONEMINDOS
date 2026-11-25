---
pr: pending
branch: claude/431-language-picker
---
UMB-P13, first slice (#431): the dashboard can now be translated. The message catalogue falls back to English one key at a time, so a half-finished translation never shows a blank. A language picker sits in Settings, under Appearance. The choice is remembered per person in this browser, and the browser's language is the default. Dates, numbers and the clock follow the chosen language, and the page language attribute is set for screen readers. A test fails if a screen that already uses messages grows a hard-coded sentence. English is still the only language shipped; the first translation is a catalogue file the founder picks.
