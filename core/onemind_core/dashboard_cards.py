# SPDX-License-Identifier: Apache-2.0
"""A personal Dashboards card stores its subject binding, and never a grant."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .auth import Principal
from .errors import SemanticValueError
from .events import DOMAIN_RE, SUBJECT_PREFIX, TOKEN
from .identity.scopes import has_any, role_scopes
from .jsonbody import JsonBody
from .ledger import Base
from .store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("dashboard_cards")

# Enroll only domains with an established read capability. New EventHub publishers
# receive no access by default. Public feeds contain event facts, never raw payloads.
DOMAIN_SCOPE = {"backup": "backups:read", "node": "nodes:read"}
NAME_TOKEN = re.compile(rf"(?:{TOKEN}|\*)")
MAX_SUBJECT = len(SUBJECT_PREFIX) + 5 * 40 + 4


def event_pattern(subject: str) -> str:
    domain, *name = subject.removeprefix(SUBJECT_PREFIX).split(".")
    if (not subject.startswith(SUBJECT_PREFIX) or not DOMAIN_RE.fullmatch(domain) or domain not in DOMAIN_SCOPE
            or not 1 <= len(name) <= 4 or name.count("*") > 1 or not all(NAME_TOKEN.fullmatch(t) for t in name)):
        raise SemanticValueError("use an enrolled gateway event subject with at most one name wildcard", "bad_subject")
    return ".".join((domain, *name))


def can_read_subject(principal: Principal, scopes: frozenset[str] | None, pattern: str) -> bool:
    required = DOMAIN_SCOPE.get(pattern.partition(".")[0])
    return principal.kind == "person" and required is not None and has_any(
        scopes if scopes is not None else role_scopes(principal.role), (required,)
    )


class SubjectSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["subject"]
    subject: str = Field(description="A gateway onemind.event subject with at most one wildcard in its name")

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, subject: str) -> str:
        event_pattern(subject)
        return subject


class SubjectCard(JsonBody):
    model_config = ConfigDict(extra="forbid")
    source: SubjectSource


class SubjectCardRow(Base):
    __tablename__ = "dashboard_subject_cards"
    person_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    subject: Mapped[str] = mapped_column(String(MAX_SUBJECT))


class SubjectCards(SqlRepository):
    def get(self, person_id: str) -> str | None:
        with self.db.session() as session:
            row = session.get(SubjectCardRow, person_id)
            return row.subject if row is not None else None

    def save(self, person_id: str, subject: str) -> bool:
        with self.db.session.begin() as session:
            stmt = self.db.insert()(SubjectCardRow).values(person_id=person_id, subject=subject)
            stmt = stmt.on_conflict_do_update(index_elements=["person_id"], set_={"subject": subject},
                                              where=SubjectCardRow.subject != subject)
            return session.scalar(stmt.returning(SubjectCardRow.person_id)) is not None
