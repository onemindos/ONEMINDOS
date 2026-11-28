# SPDX-License-Identifier: Apache-2.0
"""Release one locally staged CUPS job through the standard physical approval queue."""

from __future__ import annotations

import http.client
import re
import socket
import struct
from urllib.parse import unquote, urlsplit

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from ..actions import FeatureAction
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError
from ..executors import ExecResult

ORDER = 339
ACTION = "print.job.release"
SOCKET = "/run/cups/cups.sock"
GET_JOB_ATTRIBUTES = 0x0009
RELEASE_JOB = 0x000D


class PrintJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job: str = Field(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,126}-[1-9][0-9]{0,9}$")
    title: str = Field(pattern=r"^[0-9a-f-]{36} [ -~]{1,120}$")


class CupsConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCKET)


def _attribute(tag: int, name: str, value: str) -> bytes:
    return struct.pack("!BH", tag, len(name)) + name.encode() + struct.pack("!H", len(value)) + value.encode()


def _job_request(operation: int, job_id: str) -> bytes:
    resource = f"/jobs/{job_id}"
    request = (struct.pack("!BBHI", 2, 0, operation, 1) + b"\x01"
               + _attribute(0x47, "attributes-charset", "utf-8")
               + _attribute(0x48, "attributes-natural-language", "en")
               + _attribute(0x45, "job-uri", f"ipp://localhost{resource}")
               + _attribute(0x42, "requesting-user-name", "onemind") + b"\x03")
    with_conn = CupsConnection("localhost", timeout=5)
    try:
        with_conn.request("POST", resource, request, {"Content-Type": "application/ipp", "Authorization": "PeerCred onemind"})
        response = with_conn.getresponse()
        payload = response.read(65537)
    finally:
        with_conn.close()
    if response.status != 200 or not 9 <= len(payload) <= 65536 or payload[2:4] != b"\x00\x00":
        raise ValueError("CUPS refused the job operation")
    return payload


def _job_attributes(payload: bytes) -> dict[bytes, bytes]:
    """Read the first value of each attribute in the IPP job group."""
    result = {}
    offset, group = 8, 0
    while offset < len(payload):
        tag = payload[offset]
        offset += 1
        if tag == 3:
            return result
        if tag < 0x10:
            group = tag
            continue
        name_size, = struct.unpack_from("!H", payload, offset)
        offset += 2
        name = payload[offset:offset + name_size]
        offset += name_size
        value_size, = struct.unpack_from("!H", payload, offset)
        offset += 2
        if group == 2 and name:
            result.setdefault(name, payload[offset:offset + value_size])
        offset += value_size
    raise ValueError("incomplete IPP job response")


def _held(params: dict) -> str:
    queue, job_id = params["job"].rsplit("-", 1)
    attrs = _job_attributes(_job_request(GET_JOB_ATTRIBUTES, job_id))
    printer = unquote(urlsplit(attrs.get(b"job-printer-uri", b"").decode()).path)
    if (printer != f"/printers/{queue}" or attrs.get(b"job-name") != params["title"].encode()
            or attrs.get(b"job-originating-user-name") != b"onemind"
            or attrs.get(b"job-state") != b"\x00\x00\x00\x04"  # pending-held
            or attrs.get(b"job-hold-until") != b"indefinite"):
        raise ValueError("the requested job is not held")
    return job_id


CUPS_ERRORS = (OSError, http.client.HTTPException, ValueError, struct.error)
MISSING = "The matching held print job is unavailable. Check the job and submit it again if needed."


def _check_request(params: dict, _: Principal) -> None:
    try:
        _held(params)
    except CUPS_ERRORS:
        raise ApiError(409, "stale_precondition", MISSING, reason="print_job_unavailable") from None


def _release(action, finish) -> None:
    try:
        job_id = _held(action.params)
    except CUPS_ERRORS:
        finish(ExecResult("failed", MISSING))
        return
    try:
        _job_request(RELEASE_JOB, job_id)
    except CUPS_ERRORS:
        finish(ExecResult("outcome_unknown", "CUPS did not confirm release. Check the printer before retrying."))
        return
    finish(ExecResult("succeeded", "Released the approved job to CUPS."))


def register(_app: FastAPI, gw: Gateway) -> None:
    gw.actions.register_type(ACTION, FeatureAction(
        "actuate", _release, frozenset(), params_model=PrintJob, check_request=_check_request, physical=True,
        preview_for=lambda params: {"kind": "text", "text": f"Print {params['title'][37:]} on {params['job'].rsplit('-', 1)[0]}"},
    ))
