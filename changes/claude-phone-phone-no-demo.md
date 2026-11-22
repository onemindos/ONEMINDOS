---
pr: pending
branch: claude/phone-phone-no-demo
---
Phone app shows only the owner's real data (wave P, #827): the Try the demo buttons, the onemind://demo link and the screenshot tour that opened the demo are gone; the session always builds the HTTP client to your hub (tests still hand in the in-memory gateway through makeApi); a demo sign-in saved by an older build loads as signed out; Photo backup no longer has an in-memory box or made-up library at runtime; demo wording is gone from Settings, You and This phone. A guard test fails if any app file imports the mock gateway, its fixtures, the in-memory Photos box or the made-up library.
