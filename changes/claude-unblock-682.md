---
pr: 926
branch: claude/unblock-682
---
Notification read state on the hub (Refs #682): a read or read-all now sends a typed `notification.read` / `notification.read_all` event on `GET /v1/events` that reaches only the reader's own streams, live and on replay, and the new `GET /v1/notifications/summary` gives a person's unread count per severity in one call. The dashboard bell reacts only to notification and alert events, reads the summary again on a notification event and pulls the inbox when it moved, so marking read on one device clears the bell on another within 2 s. Phone part left to wave P.
