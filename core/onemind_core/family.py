# SPDX-License-Identifier: Apache-2.0
"""FAM-01: owner-managed family policy, intersected with existing app sharing."""
from __future__ import annotations

from datetime import date
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .context import Gateway
from .errors import ApiError
from .identity import ctx_of
from .identity.models import IdentityRepository
from .ledger import Base
from .store import FeatureSchema

SCHEMA = FeatureSchema("family")
AppId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")]
Tag = Annotated[str, Field(min_length=1, max_length=64)]
# Roles that carry per-person limits and a birth date (age assurance, California AB 1043 from 2027).
AGE_ASSURED_ROLES = ("child", "teen")


class Window(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: list[Annotated[int, Field(ge=0, le=6)]] = Field(min_length=1, max_length=7, description="Monday=0; start day for overnight windows")
    start_minute: int = Field(ge=0, le=1439)
    end_minute: int = Field(ge=0, le=1440, description="Exclusive end; less than start means overnight")

    @model_validator(mode="after")
    def nonempty(self):
        if self.start_minute == self.end_minute:
            raise ValueError("window must have a nonzero duration")
        return self


class FamilyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    birth_date: date | None = Field(default=None, description="Private child or teen profile data; never included in audit events")
    allowed_apps: list[AppId] | None = Field(default=None, max_length=500, description="Null inherits sharing; empty denies all apps; never grants access")
    max_age_rating: int | None = Field(default=None, ge=0, le=21, description="Maximum app minimum-age rating; unclassified apps are blocked when set")
    blocked_tags: list[Tag] = Field(default_factory=list, max_length=100)
    timezone: str = Field(default="UTC", max_length=100)
    windows: list[Window] | None = Field(default=None, max_length=50, description="Null allows all times; empty denies all times; evaluated in timezone")

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("unknown IANA timezone") from None
        return value


class AppClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_age: int | None = Field(default=None, ge=0, le=21)
    tags: list[Tag] = Field(default_factory=list, max_length=100)


class ProfileRow(Base):
    __tablename__ = "family_profiles"
    user_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    policy: Mapped[dict] = mapped_column(JSON)


class ClassificationRow(Base):
    __tablename__ = "family_app_classifications"
    app_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    policy: Mapped[dict] = mapped_column(JSON)


class FamilyService:
    def __init__(self, gw: Gateway, identity):
        self.gw, self.identity = gw, identity
        self.repo = IdentityRepository(gw.db)

    def target(self, p, user_id):
        self.identity._owner_only(p, "manage family controls")
        user = self.identity.user(user_id)
        if user is None:
            raise ApiError(404, "not_found", "no such user")
        return user

    def profile(self, p, user_id):
        self.target(p, user_id)
        row = self.repo.get(ProfileRow, user_id)
        return FamilyProfile.model_validate(row.policy) if row else FamilyProfile()

    def put_profile(self, ctx, p, user_id, policy):
        user = self.target(p, user_id)
        if user.role == "owner":
            raise ApiError(422, "conflict", "owners cannot be restricted")
        if policy.birth_date is not None and (user.role not in AGE_ASSURED_ROLES or policy.birth_date > self.gw.clock().date()):
            raise ApiError(422, "conflict", "birth date must be a nonfuture date on a child or teen profile")
        if policy.allowed_apps is not None and set(policy.allowed_apps) - self.gw.catalog.load().keys():
            raise ApiError(422, "conflict", "allowlist contains an unknown app")
        via = self.identity.require_step_up(ctx, p, "manage family controls")
        self.save(ProfileRow, user_id, policy)
        self.identity.emit("family", "profile.updated", {"user_id": user_id, "step_up": via}, p)
        return policy

    def classification(self, p, app_id):
        self.identity._owner_only(p, "manage app classifications")
        if app_id not in self.gw.catalog.load():
            raise ApiError(404, "not_found", "no such app")
        row = self.repo.get(ClassificationRow, app_id)
        return AppClassification.model_validate(row.policy) if row else AppClassification()

    def put_classification(self, ctx, p, app_id, policy):
        self.classification(p, app_id)
        via = self.identity.require_step_up(ctx, p, "manage app classifications")
        self.save(ClassificationRow, app_id, policy)
        self.identity.emit("family", "classification.updated", {"app_id": app_id, "step_up": via}, p)
        return policy

    def save(self, cls, key, policy):
        with self.repo.db.session.begin() as s:
            row = s.get(cls, key)
            data = policy.model_dump(mode="json")
            if row is None:
                field = "user_id" if cls is ProfileRow else "app_id"
                s.add(cls(**{field: key, "policy": data}))
            else:
                row.policy = data

    def app_filter(self, request, p, app_id):
        # An owned agent token must not bypass its person's sharing or family restrictions.
        ctx = ctx_of(request)
        if p.kind != "person":
            owner_id = ctx.token.owner_user_id if ctx and ctx.token else None
            if owner_id is None:
                return True
            owner = self.identity.user(owner_id)
            if owner is None or owner.disabled:
                return False
            p = self.identity.principal_for(owner)
            if not self.identity.can_open(p, app_id):
                return False
        if p.is_owner:
            return True
        row = self.repo.get(ProfileRow, p.id)
        if row is None:
            return True
        policy = FamilyProfile.model_validate(row.policy)
        if policy.allowed_apps is not None and app_id not in policy.allowed_apps:
            return False
        classification = self.repo.get(ClassificationRow, app_id)
        labels = AppClassification.model_validate(classification.policy) if classification else AppClassification()
        if policy.max_age_rating is not None and (labels.min_age is None or labels.min_age > policy.max_age_rating):
            return False
        if {t.casefold() for t in policy.blocked_tags} & {t.casefold() for t in labels.tags}:
            return False
        if policy.windows is None:
            return True
        local = self.gw.clock().astimezone(ZoneInfo(policy.timezone))
        minute, day = local.hour * 60 + local.minute, local.weekday()
        for window in policy.windows:
            start, end = window.start_minute, window.end_minute
            if start < end:
                if day in window.days and start <= minute < end:
                    return True
            elif (day in window.days and minute >= start) or ((day - 1) % 7 in window.days and minute < end):
                return True
        return False
