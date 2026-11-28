# SPDX-License-Identifier: Apache-2.0
"""Attach plugin credential retirement after identity storage is available."""
from fastapi import FastAPI

from ..context import Gateway
from ..plugins.credentials import register_credentials
from ..plugins.workload import register_workloads

ORDER = 265


def register(app: FastAPI, gw: Gateway) -> None:
    register_credentials(gw, app.state.identity)
    register_workloads(gw, app.state.identity)
