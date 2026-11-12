# SPDX-License-Identifier: Apache-2.0
"""Household identity (contract §12.6). Importing registers the tables and the settings section."""

from .models import SCHEMA
from .service import AuthContext, IdentityService, ctx_of
from .settings import IdentitySettings

__all__ = ["SCHEMA", "AuthContext", "IdentityService", "IdentitySettings", "ctx_of"]
