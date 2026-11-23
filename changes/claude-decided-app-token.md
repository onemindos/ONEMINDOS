---
pr: pending
branch: claude/decided-app-token
---
The app proxy now lets an app keep its own sign-in token (issue 824, so Fleetbase can be packaged). Behind a valid OneMind session cookie, the Authorization header a browser app sends belongs to that app: it never signs anyone in to OneMind, and it is forwarded to that app only. A OneMind token in that header (any om_ token, or any token the gateway knows) is never forwarded, a request with only an app token is refused with 401, and the session cookie now decides who the person is ahead of a bearer token. OneMind API routes keep their own rules.
