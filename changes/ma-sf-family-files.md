---
pr: 1321
branch: ma/sf-family-files
---
Family members can use Files and Photos for their own data (Refs #1232, Refs #234). The new person-only Files and Photos scopes let family sessions reach the gateway's role and space checks. Owner, adult, teen and child can use their own Home, restore files from Home trash and back up their own Photos library. Guests can browse Shared, and only owners and adults can write to Shared or use its trash. Chunked Sync uploads and permanent trash-empty requests remain owner-scoped for signed-in sessions. The Files dashboard uses the role from sign-in and offers folder access requests and request review to owners. Concurrent Photos uploads reserve space against one disk budget. The desktop restores saved windows after routing is ready. Gateway tests use real sign-ins, and dashboard tests use mocked sessions and transport.
