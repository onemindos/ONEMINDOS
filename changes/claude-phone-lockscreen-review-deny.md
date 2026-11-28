---
pr: 909
branch: claude/phone-lockscreen-review-deny
---
Phone app (issue 704). Approval notifications offer Review and Deny, both requiring device unlock. Review opens the named approval card, including from a cold start. Deny checks that the request is still pending and asks for confirmation showing its title and ID before recording the denial. Settings offers Lock OneMind, which protects the app-switcher preview and locks on launch or after 30 seconds in the background. The lock hides OneMind from screen readers and holds incoming file shares until the app is accessible.
