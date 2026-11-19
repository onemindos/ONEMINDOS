# SPDX-License-Identifier: Apache-2.0
"""NMD-07 (#132): the owner's update policy for apps, and its dry run (automation/updatepolicy.py).

`GET /v1/update-policy` shows the knobs (computed defaults until the owner changes them) and the
apps whose auto-update is paused after failures; `PUT` changes them (owner only);
`GET /v1/update-policy/dry-run` answers "what would update tonight" and files nothing;
`POST /v1/update-policy/resume` lifts a back-off for one app (owner only).
"""

from __future__ import annotations

from fastapi import Depends, FastAPI

from ..auth import Principal
from ..automation.updatepolicy import ResumeBody, UpdatePolicyBody, UpdatePolicyService
from ..context import Gateway
from ..errors import error_responses
from ..identity.scopes import register_route_scope

# After automation (280): it uses the automation service's windows and standing approvals.
ORDER = 285

# What a scoped token needs (identity/scopes.py): reading is an update or automation read; changing
# the policy or lifting a back-off is `updates:admin`, which only the owner role holds.
register_route_scope("GET,HEAD", r"/v1/update-policy(/dry-run)?", ("updates:read", "automation:read"))
register_route_scope("PUT", r"/v1/update-policy", ("updates:admin",))
register_route_scope("POST", r"/v1/update-policy/resume", ("updates:admin",))


def register(app: FastAPI, gw: Gateway) -> None:
    principal = gw.principal
    svc = UpdatePolicyService(gw, app.state.automation)
    svc.automation.policies.update_gate = svc.gate
    app.state.update_policy = svc
    tags = ["updates"]

    @app.get("/v1/update-policy", operation_id="update_policy.get", tags=tags, responses=error_responses(401))
    def get_update_policy(_: Principal = Depends(principal)):
        """The owner's update policy for apps, and the apps whose auto-update is paused."""
        return svc.to_json()

    @app.put("/v1/update-policy", operation_id="update_policy.put", tags=tags, responses=error_responses(401, 403, 422))
    def put_update_policy(body: UpdatePolicyBody, p: Principal = Depends(principal)):
        """Change the update policy (owner only). The knobs only ever hold an update back."""
        return svc.put(p, body)

    @app.get("/v1/update-policy/dry-run", operation_id="update_policy.dry_run", tags=tags, responses=error_responses(401))
    def update_policy_dry_run(_: Principal = Depends(principal)):
        """What would update in the next maintenance window, app by app, and why not. Files nothing."""
        return svc.dry_run()

    @app.post("/v1/update-policy/resume", operation_id="update_policy.resume", tags=tags, responses=error_responses(401, 403, 422))
    def resume_auto_update(body: ResumeBody, p: Principal = Depends(principal)):
        """Lift the back-off for one app (owner only): its failed updates before now stop counting."""
        return svc.resume(p, body.app_id)
