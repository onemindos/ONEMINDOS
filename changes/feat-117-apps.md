---
pr: pending
branch: feat/117-apps
---
App-gate smoke diagnostics now collect each init and app container separately, including previous init crashes and current kubectl errors, while retaining Secret-value redaction and the original gate verdict. This exposes initialization failures that previously produced empty pod logs; it does not unblock apps or complete the catalogue-wide gate acceptance in issue #117.
