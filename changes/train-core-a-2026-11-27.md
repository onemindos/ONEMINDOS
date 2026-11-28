---
pr: 1322
branch: train/core-a-2026-11-27
---
Founder-authorized core-a merge train (Refs #234). Round 1 adds the missing Work and permissions callers, streams the journal through the SDK, and makes permission increases wait for action-bound owner approval (D-028). Stop reports incomplete enforcement when policy delivery fails, and actuating jobs require current gateway confirmation just before dispatch (D-029). Previously enrolled leaves must rejoin to refresh their NATS permissions for that check. The constituent fragments record the scope of the original changes.
