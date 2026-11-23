---
pr: 928
branch: claude/ab2-share-types
---
Send to (#612, first part): a share type registry (note, task, event, person, file, place, track, alert, clip, the same list as the descriptor enum), each with the data grant it needs, and three gateway routes. GET /v1/share/types lists the types, GET /v1/share/targets lists the switched-on apps you can see that accept a type and hold its grant (today Files and Photos for a file), and POST /v1/share hands one object reference to one app as the audited share.sent event on the bus, with a per-object deep link onemind://app/type/ref. It refuses an app that does not accept the type or verb, an app without the type's data grant (a place needs the location grant), a switched-off or unseen app, and any agent: an agent may list targets, but only an owner or adult sends. The desktop onemind:// handler follows in a second PR on the same issue.
