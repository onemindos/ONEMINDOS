---
pr: 924
branch: claude/d12-tainted-input
---
AIG-04 (#168): an agent that read third-party text (app descriptions, node names, audit notes), through MCP or any REST read except the box's own instance info, is tainted for an hour. Everything it then requests, app actions and feature actions such as system controls and MCP built-in tools alike, is filed with a taint note on the approval card (shown first, high risk, naming what it read) and in the audit log, is never accepted by a standing approval, can only be approved by the owner naming the exact plan fingerprint, and may only target apps whose aiPolicy shows them to AI. Injection test: a hostile app description tells the agent to remove an app; the agent obeys and the request still waits for a person. Carries PR #480 forward onto release/next.
