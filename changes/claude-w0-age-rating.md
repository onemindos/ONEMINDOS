---
pr: 918
branch: claude/w0-age-rating
---
Lands the W0 train of approved PRs (#307 #347 #349 #362 #368 #377 #378 #379 #381 #383 #399 #402 #454 #455 #456 #480 #489) on top of current release/next, and gives the six apps that had no age rating one now that #456 makes it required: Chromium and Firefox are 18 (an unfiltered web browser that opens any site and keeps saved logins), and the Modbus, BACnet, CAN and OPC UA adapters are 18 (device access). The Go plugin validator fixture and the `onemind plugin` scaffold now carry a rating too, so the Go tests and newly scaffolded plugins pass the schema.
