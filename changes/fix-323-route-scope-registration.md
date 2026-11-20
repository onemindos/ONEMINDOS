---
pr: pending
branch: fix/323-route-scope-registration
---
CORE-HYG-01 (#323): register Home and machine route scopes once at module import, preventing repeated gateway creation from growing the global authorization table. Regression coverage checks registry stability, route inventory, and unchanged scope requirements, including fail-closed fallbacks. Stacked on the machine actions work in #340; changes no handlers or approval policy (D-014).
