# SPDX-License-Identifier: Apache-2.0
"""Automation: schedules, event rules, standing approvals, windows, dry run and kill switch.

Contract §12.17; design in docs/architecture/AUTOMATION.md and docs/leap/core/AUTOMATION.md.
A rule only ever requests actions (as `automation:<rule-id>`); approval comes from the owner or
from a standing approval the owner set (`approved_by: policy:<id>@<revision>`).
"""

from .engine import AutomationService, AutomationSettings
from .policies import PolicyService

__all__ = ["AutomationService", "AutomationSettings", "PolicyService"]
