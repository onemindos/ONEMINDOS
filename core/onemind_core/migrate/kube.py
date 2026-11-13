# SPDX-License-Identifier: Apache-2.0
"""A Kubernetes API client for the OLD cluster, fenced to the verbs the migration kit needs.

The owner hands the gateway a kubeconfig for the cluster they are moving off. This module:

- parses it without ever touching the gateway's own files or running anything: `exec` and
  `auth-provider` plugins, file references (`certificate-authority`, `tokenFile`, ...),
  `insecure-skip-tls-verify`, `proxy-url` and plain http are refused;
- keeps the credential in memory only (`KubeTarget` hides it from repr and is never stored);
- sends every request through one fence. Reading a namespace uses GET on a fixed list of
  namespaced paths and nothing else; Secrets are never read at all (their names come from the
  workloads that reference them). The copy step may additionally create and delete its own
  helper pods (name prefix `onemind-migrate-`) and read their logs; the switch-over step may
  additionally set `replicas` through the `scale` subresource. Anything else raises FenceError
  before a byte leaves the box.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import ipaddress
import json
import os
import re
import ssl
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import quote, urlencode, urlsplit

import yaml

MAX_KUBECONFIG_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
HELPER_PREFIX = "onemind-migrate-"
HELPER_LABEL = "onemind.io/migrate-helper"

# What a step may do on the old cluster. READ is always allowed.
READ, HELPER, SCALE = "read", "helper", "scale"


class KubeconfigError(ValueError):
    """The kubeconfig is malformed or asks for something the gateway never does."""


class FenceError(PermissionError):
    """A request outside the verbs this step was granted; never sent."""


class KubeApiError(Exception):
    def __init__(self, status: int, path: str, message: str):
        super().__init__(f"HTTP {status} on {path}: {message}")
        self.status = status
        self.path = path
        self.message = message


class KubeUnreachable(Exception):
    pass


@dataclass(frozen=True)
class KubeTarget:
    """One cluster and one identity, from the chosen kubeconfig context. Held in memory only."""

    server: str
    context: str
    namespace: str | None
    ca_pem: str | None = field(default=None, repr=False)
    token: str | None = field(default=None, repr=False)
    client_cert_pem: str | None = field(default=None, repr=False)
    client_key_pem: str | None = field(default=None, repr=False)

    @property
    def fingerprint(self) -> str:
        """sha256 of server and identity: lets the audit tell credentials apart without holding them."""
        h = hashlib.sha256()
        for part in (self.server, self.token or "", self.client_cert_pem or ""):
            h.update(part.encode() + b"\0")
        return "sha256:" + h.hexdigest()

    @property
    def server_host(self) -> str:
        return urlsplit(self.server).hostname or ""


def _b64(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise KubeconfigError(f"{what} must be base64 text")
    try:
        return base64.b64decode(value, validate=True).decode()
    except (ValueError, UnicodeDecodeError):
        raise KubeconfigError(f"{what} is not valid base64 PEM") from None


def _named(doc: dict, key: str, name: str) -> dict:
    for entry in doc.get(key) or []:
        if isinstance(entry, dict) and entry.get("name") == name:
            inner = entry.get(key[:-1])
            if isinstance(inner, dict):
                return inner
    raise KubeconfigError(f"kubeconfig has no {key[:-1]} named {name!r}")


FILE_KEYS = ("certificate-authority", "client-certificate", "client-key", "tokenFile")
REFUSED_USER_KEYS = {
    "exec": "exec credential plugins run commands; the gateway never runs anything from a kubeconfig",
    "auth-provider": "auth-provider plugins are not supported",
    "username": "basic auth is not supported; use a ServiceAccount token (onemind migrate role)",
    "password": "basic auth is not supported; use a ServiceAccount token (onemind migrate role)",
    "as": "impersonation is not supported",
    "as-groups": "impersonation is not supported",
}


def parse_kubeconfig(text: str, context: str | None = None) -> KubeTarget:
    """Pick one context and return its target. Raises KubeconfigError with a plain-language reason."""
    if len(text.encode()) > MAX_KUBECONFIG_BYTES:
        raise KubeconfigError(f"kubeconfig is larger than {MAX_KUBECONFIG_BYTES // 1024} KiB")
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        raise KubeconfigError("kubeconfig is not valid YAML") from None
    if not isinstance(doc, dict) or doc.get("kind", "Config") != "Config":
        raise KubeconfigError("not a kubeconfig (kind: Config)")
    name = context or doc.get("current-context")
    if not isinstance(name, str) or not name:
        raise KubeconfigError("no context given and no current-context in the kubeconfig")
    ctx = _named(doc, "contexts", name)
    cluster = _named(doc, "clusters", str(ctx.get("cluster")))
    user = _named(doc, "users", str(ctx.get("user")))

    for key in FILE_KEYS:
        if key in cluster or key in user:
            raise KubeconfigError(
                f"{key} points at a file; send a self-contained kubeconfig "
                "(kubectl config view --minify --flatten --raw)"
            )
    for key, why in REFUSED_USER_KEYS.items():
        if key in user:
            raise KubeconfigError(f"users.{key}: {why}")
    if cluster.get("insecure-skip-tls-verify"):
        raise KubeconfigError("insecure-skip-tls-verify is refused: the cluster certificate must be checked")
    if cluster.get("proxy-url") or cluster.get("tls-server-name"):
        raise KubeconfigError("proxy-url and tls-server-name are not supported")
    server = cluster.get("server")
    parts = urlsplit(server) if isinstance(server, str) else None
    if parts is None or parts.scheme != "https" or not parts.hostname:
        raise KubeconfigError("cluster server must be an https:// URL")
    if parts.path not in ("", "/") or parts.query:
        raise KubeconfigError("cluster server must be scheme://host[:port] with no path")
    try:
        ip = ipaddress.ip_address(parts.hostname.strip("[]"))
    except ValueError:
        ip = None  # a DNS name
    if ip is not None and (ip.is_link_local or ip.is_unspecified or ip.is_multicast):
        # Cloud metadata services live on link-local addresses (169.254.169.254): a kubeconfig
        # must never turn the gateway into a client of those.
        raise KubeconfigError("cluster server must not be a link-local, unspecified or multicast address")
    ca = cluster.get("certificate-authority-data")
    ca_pem = _b64(ca, "certificate-authority-data") if ca is not None else None
    token = user.get("token")
    cert = user.get("client-certificate-data")
    key = user.get("client-key-data")
    if token is not None and not (isinstance(token, str) and token.strip()):
        raise KubeconfigError("users.token must be a non-empty string")
    if (cert is None) != (key is None):
        raise KubeconfigError("client-certificate-data and client-key-data go together")
    if token is None and cert is None:
        raise KubeconfigError("the user has no token and no client certificate")
    ns = ctx.get("namespace")
    return KubeTarget(
        server=f"https://{parts.netloc}",
        context=name,
        namespace=ns if isinstance(ns, str) and NAME_RE.match(ns) else None,
        ca_pem=ca_pem,
        token=token.strip() if isinstance(token, str) else None,
        client_cert_pem=_b64(cert, "client-certificate-data") if cert is not None else None,
        client_key_pem=_b64(key, "client-key-data") if key is not None else None,
    )


# ---- the fence -------------------------------------------------------------------------------
_N = r"[a-z0-9]([-a-z0-9.]*[a-z0-9])?"
READ_PATHS = [re.compile(p) for p in (
    r"^/version$",
    rf"^/api/v1/namespaces/(?P<ns>{_N})/(pods|services|persistentvolumeclaims|configmaps)$",
    rf"^/apis/apps/v1/namespaces/(?P<ns>{_N})/(deployments|statefulsets|daemonsets)$",
    rf"^/apis/networking\.k8s\.io/v1/namespaces/(?P<ns>{_N})/ingresses$",
    rf"^/apis/batch/v1/namespaces/(?P<ns>{_N})/(jobs|cronjobs)$",
    rf"^/api/v1/namespaces/(?P<ns>{_N})/pods/(?P<name>{_N})$",
    rf"^/apis/apps/v1/namespaces/(?P<ns>{_N})/(deployments|statefulsets)/(?P<name>{_N})$",
)]
HELPER_LOG = re.compile(rf"^/api/v1/namespaces/(?P<ns>{_N})/pods/(?P<name>{_N})/log$")
HELPER_CREATE = re.compile(rf"^/api/v1/namespaces/(?P<ns>{_N})/pods$")
HELPER_DELETE = re.compile(rf"^/api/v1/namespaces/(?P<ns>{_N})/pods/(?P<name>{_N})$")
SCALE = re.compile(rf"^/apis/apps/v1/namespaces/(?P<ns>{_N})/(deployments|statefulsets)/(?P<name>{_N})/scale$")


def fence(method: str, path: str, namespace: str, grants: frozenset[str]) -> None:
    """Raise FenceError unless (method, path) is allowed for this namespace and these grants."""

    def same_ns(m: re.Match) -> bool:
        return m.groupdict().get("ns") in (None, namespace)

    if method == "GET":
        for rx in READ_PATHS:
            m = rx.match(path)
            if m and same_ns(m):
                return
        m = HELPER_LOG.match(path)
        if m and same_ns(m) and HELPER in grants and m["name"].startswith(HELPER_PREFIX):
            return
    elif method == "POST" and HELPER in grants:
        m = HELPER_CREATE.match(path)
        if m and same_ns(m):
            return
    elif method == "DELETE" and HELPER in grants:
        m = HELPER_DELETE.match(path)
        if m and same_ns(m) and m["name"].startswith(HELPER_PREFIX):
            return
    elif method == "PATCH" and SCALE in grants:
        m = SCALE.match(path)
        if m and same_ns(m):
            return
    raise FenceError(f"{method} {path} is outside what this migration step may do")


# A transport sends one request: (method, url, headers, body) -> (status, body). Tests replace it.
Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes]]


def _https_transport(target: KubeTarget, timeout_s: float) -> Transport:
    ctx = ssl.create_default_context(cadata=target.ca_pem) if target.ca_pem else ssl.create_default_context()
    if target.client_cert_pem and target.client_key_pem:
        # ssl only loads a client certificate from files: write both to a private temporary
        # directory, load them, and remove them before any request is made.
        with tempfile.TemporaryDirectory(prefix="onemind-migrate-") as tmp:
            os.chmod(tmp, 0o700)
            cert, key = os.path.join(tmp, "c.pem"), os.path.join(tmp, "k.pem")
            for path, data in ((cert, target.client_cert_pem), (key, target.client_key_pem)):
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write(data)
            ctx.load_cert_chain(cert, key)
    parts = urlsplit(target.server)

    def send(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
        conn = http.client.HTTPSConnection(parts.hostname, parts.port or 443, timeout=timeout_s, context=ctx)
        try:
            conn.request(method, url, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise KubeApiError(resp.status, url, "response too large")
            return resp.status, data
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            raise KubeUnreachable(f"{target.server_host}: {exc.__class__.__name__}: {exc}") from None
        finally:
            conn.close()

    return send


class KubeClient:
    """Requests against one namespace of the old cluster, each checked by fence() first."""

    def __init__(
        self,
        target: KubeTarget,
        namespace: str,
        *,
        grants: frozenset[str] = frozenset(),
        timeout_s: float = 30,
        transport: Transport | None = None,
    ):
        if not NAME_RE.match(namespace) or len(namespace) > 63:
            raise ValueError("namespace must be a DNS label")
        unknown = set(grants) - {HELPER, SCALE}
        if unknown:
            raise ValueError(f"unknown grants {sorted(unknown)}")
        self.target = target
        self.namespace = namespace
        self.grants = frozenset(grants)
        self._send = transport or _https_transport(target, timeout_s)
        self.sent: list[tuple[str, str]] = []  # (method, path) of every request made, for the step result

    def _request(self, method: str, path: str, query: dict | None = None, body: dict | None = None,
                 content_type: str = "application/json") -> bytes:
        fence(method, path, self.namespace, self.grants)
        url = path + ("?" + urlencode(query) if query else "")
        headers = {"Accept": "application/json", "User-Agent": "onemind-migrate/1"}
        if self.target.token:
            headers["Authorization"] = f"Bearer {self.target.token}"
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = content_type
        self.sent.append((method, path))
        status, raw = self._send(method, url, headers, data)
        if status >= 400:
            msg = ""
            try:
                msg = json.loads(raw).get("message", "")
            except (ValueError, AttributeError):
                msg = raw[:200].decode("utf-8", "replace")
            raise KubeApiError(status, path, msg or "error")
        return raw

    def _json(self, method: str, path: str, **kw) -> dict:
        raw = self._request(method, path, **kw)
        try:
            doc = json.loads(raw)
        except ValueError:
            raise KubeApiError(502, path, "response is not JSON") from None
        if not isinstance(doc, dict):
            raise KubeApiError(502, path, "response is not a JSON object")
        return doc

    # ---- read ------------------------------------------------------------------------------
    def version(self) -> dict:
        return self._json("GET", "/version")

    def list(self, api: str, resource: str) -> list[dict]:
        """api is "" for core/v1, else the group/version (apps/v1, networking.k8s.io/v1, batch/v1)."""
        prefix = "/api/v1" if not api else f"/apis/{api}"
        doc = self._json("GET", f"{prefix}/namespaces/{quote(self.namespace)}/{resource}")
        items = doc.get("items")
        return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []

    def get_pod(self, name: str) -> dict:
        return self._json("GET", f"/api/v1/namespaces/{quote(self.namespace)}/pods/{quote(name)}")

    def get_workload(self, kind: str, name: str) -> dict:
        res = {"Deployment": "deployments", "StatefulSet": "statefulsets"}[kind]
        return self._json("GET", f"/apis/apps/v1/namespaces/{quote(self.namespace)}/{res}/{quote(name)}")

    # ---- helper pods (grant HELPER) -------------------------------------------------------
    def create_helper_pod(self, pod: dict) -> dict:
        md = pod.get("metadata") or {}
        name = md.get("name", "")
        if not str(name).startswith(HELPER_PREFIX) or HELPER_LABEL not in (md.get("labels") or {}):
            raise FenceError("only OneMind migration helper pods may be created")
        if md.get("namespace") not in (None, self.namespace):
            raise FenceError("helper pod namespace differs from the plan's namespace")
        return self._json("POST", f"/api/v1/namespaces/{quote(self.namespace)}/pods", body=pod)

    def delete_helper_pod(self, name: str) -> None:
        try:
            self._request("DELETE", f"/api/v1/namespaces/{quote(self.namespace)}/pods/{quote(name)}")
        except KubeApiError as exc:
            if exc.status != 404:
                raise

    def helper_log(self, name: str, tail_lines: int = 200) -> str:
        raw = self._request(
            "GET", f"/api/v1/namespaces/{quote(self.namespace)}/pods/{quote(name)}/log",
            query={"tailLines": str(tail_lines)},
        )
        return raw.decode("utf-8", "replace")

    # ---- scale (grant SCALE) ----------------------------------------------------------------
    def scale(self, kind: str, name: str, replicas: int) -> None:
        res = {"Deployment": "deployments", "StatefulSet": "statefulsets"}[kind]
        if not isinstance(replicas, int) or replicas < 0:
            raise ValueError("replicas must be >= 0")
        self._request(
            "PATCH", f"/apis/apps/v1/namespaces/{quote(self.namespace)}/{res}/{quote(name)}/scale",
            body={"spec": {"replicas": replicas}}, content_type="application/merge-patch+json",
        )
