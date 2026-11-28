# SPDX-License-Identifier: Apache-2.0
"""WebDAV for Finder and Linux file managers, LAN and mesh only (files-webdav, #722).

Finder (Go > Connect to Server, `https://onemind.local/dav/`) and GNOME Files or KDE
(`davs://onemind.local/dav/`) mount a person's Files spaces with an app password
(files/apppasswords.py). Windows is pointed to SMB instead (routers/shares.py): Microsoft has
deprecated its WebDAV client (WebClient service).

Layout: `/dav/Home/...` is the person's own Home (`home:<person>`), `/dav/Shared/...` the household
Shared folder. Each is there only when the app password's scopes include it.

Why a middleware and not routes: the gateway guard caps every request body at 256 KiB and rate
limits per address (guard.py, §12.1). A Finder upload is one PUT of the whole file, sent chunked,
and Finder sends many small requests when it opens a folder. So `/dav` is answered here, outside
the guard, with its own limits: a body is streamed to disk (never buffered) up to the Files upload
limit and the space's quota; requests are rate limited per app password; wrong passwords back off
per address; and responses carry the guard's security headers with a sandboxing CSP, so a page
stored in Files can never run as the gateway's origin.

Rules (the acceptance test of #722, core/tests/test_files_webdav.py):
- **LAN and mesh only.** The socket peer and the local address it reached must both be LAN or mesh
  (netpath.py); behind a trusted edge, the edge's X-OneMind-Path. Anything else gets 404 without an
  auth challenge, so the internet cannot even tell WebDAV is there.
- **App passwords only.** Gateway tokens (owner, adult, agent) are refused as Basic passwords and as
  Bearer headers (audited as webdav.token_refused, never the token); no anonymous or guest access.
- **Path confinement** is FilesService's: names are validated as text and every folder is opened
  with O_NOFOLLOW from the space's own descriptor (files/paths.py). A Destination outside /dav is 400.
- **Revocation is immediate:** the app password row is looked up on every request.
- **Cloud folders are read-only:** `Cloud/` at the top of a space is where cloud imports mirror
  (#680, one-way); a write there would be overwritten or deleted by the next sync, so it is refused.
- Deletes and overwrites go to the Trash, as in the Files app.

Locks (class 2) are advisory: LOCK answers a token so that Finder mounts read-write, but the box does
not hold them; two clients writing one file is last-writer-wins, as with SMB without oplocks.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import logging
import os
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import formatdate
from urllib.parse import quote, unquote, urlsplit
from xml.sax.saxutils import escape

from starlette.datastructures import Headers
from starlette.responses import Response, StreamingResponse

from ..auth import Principal, token_hash
from ..guard import SECURITY_HEADERS, AuthFailures, TokenBuckets
from ..netconf import NetSettings
from ..netpath import PathClassifier, parse_networks, path_of_peer
from ..sections import config_section
from . import paths
from .apppasswords import CREATE_ROLES, AppPasswordRow, AppPasswords
from .errors import FilesError, conflict, denied
from .preview import guess_mime
from .service import FilesService
from .store import new_id

log = logging.getLogger("onemind.files.webdav")

PREFIX = "/dav"
SPACES = {"Home": "home", "Shared": "shared"}   # URL name -> space kind
NAMES = {v: k for k, v in SPACES.items()}
CLOUD_DIR = "Cloud"
REACH = frozenset({"lan", "mesh"})
ALLOW = "OPTIONS, PROPFIND, GET, HEAD, PUT, DELETE, MKCOL, MOVE, COPY, LOCK, UNLOCK"
SMALL_BODY = 64 * 1024        # PROPFIND and LOCK bodies are read and dropped (all properties are always sent)
CHUNK = 1024 * 1024
CSP = "default-src 'none'; sandbox"
REALM = 'Basic realm="OneMind Files", charset="UTF-8"'


@config_section("webdav")
@dataclass(frozen=True)
class WebDavSettings:
    enabled: bool = True              # ONEMIND_WEBDAV_ENABLED=0 turns /dav off for the whole box
    request_rate: float = 50.0        # ONEMIND_WEBDAV_REQUEST_RATE: requests per second per app password
    request_burst: int = 500          # ONEMIND_WEBDAV_REQUEST_BURST: Finder opening a big folder
    auth_failures_per_min: int = 10   # ONEMIND_WEBDAV_AUTH_FAILURES_PER_MIN: wrong passwords per address
    auth_backoff_s: int = 900         # ONEMIND_WEBDAV_AUTH_BACKOFF_S

    def validate(self) -> None:
        if self.request_rate <= 0 or self.request_burst < 1:
            raise ValueError("ONEMIND_WEBDAV_REQUEST_RATE and _REQUEST_BURST must be positive")
        if self.auth_failures_per_min < 1 or self.auth_backoff_s < 1:
            raise ValueError("ONEMIND_WEBDAV_AUTH_FAILURES_PER_MIN and _AUTH_BACKOFF_S must be at least 1")


class DavError(Exception):
    def __init__(self, status: int, message: str = "", headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status, self.message, self.headers = status, message, headers or {}


@dataclass(frozen=True)
class Place:
    kind: str | None              # home | shared; None for /dav/ itself
    root: str | None              # home:<person> | shared
    parts: tuple[str, ...] = ()

    @property
    def path(self) -> str:
        return paths.join(self.parts)

    def href(self, is_dir: bool) -> str:
        if self.kind is None:
            return PREFIX + "/"
        tail = "/".join([NAMES[self.kind], *self.parts])
        return quote(f"{PREFIX}/{tail}") + ("/" if is_dir else "")


def is_dav_path(path: str) -> bool:
    return path == PREFIX or path.startswith(PREFIX + "/")


def text(status: int, body: str = "", headers: dict[str, str] | None = None) -> Response:
    return Response(body, status_code=status, media_type="text/plain; charset=utf-8", headers=headers)


def http_date(ts: float) -> str:
    return formatdate(ts, usegmt=True)


class WebDav:
    def __init__(self, gw, files: FilesService | None = None):
        self.gw = gw
        self.settings = gw.settings.section(WebDavSettings)
        self.files = files or FilesService(gw)
        self.passwords = AppPasswords(gw)
        self.classify = PathClassifier(parse_networks(gw.settings.section(NetSettings).trusted_proxies))
        self.buckets = TokenBuckets(self.settings.request_rate, self.settings.request_burst, time.monotonic)
        self.failures = AuthFailures(self.settings.auth_failures_per_min, self.settings.auth_backoff_s, time.monotonic)

    # ---- who may reach it at all --------------------------------------------------------------
    def reaches(self, scope, headers: Headers) -> bool:
        peer = (scope.get("client") or (None,))[0]
        if self.classify.trusts(peer):
            return self.classify(peer, headers) in REACH
        local = (scope.get("server") or (None,))[0]
        return path_of_peer(peer) in REACH and path_of_peer(local) in REACH

    def _gateway_token(self, secret: str) -> bool:
        return (self.gw.tokens.lookup(secret, include_retired=True) is not None
                or self.gw.repo.agent_principal_for(token_hash(secret)) is not None)

    def authenticate(self, headers: Headers, source: str) -> tuple[Principal, AppPasswordRow] | Response:
        challenge = text(401, "An app password is needed (Settings > App passwords).", {"WWW-Authenticate": REALM})
        scheme, _, value = headers.get("authorization", "").partition(" ")
        if scheme.lower() != "basic":
            if scheme.lower() == "bearer":
                self.gw.audit.append("webdav.token_refused", None, None, {"source": source, "via": "bearer"})
            return challenge
        try:
            user, _, secret = base64.b64decode(value.strip(), validate=True).decode("utf-8").partition(":")
        except (binascii.Error, UnicodeDecodeError):
            user = secret = ""
        row = self.passwords.check(user, secret) if user and secret else None
        if row is None:
            if secret and self._gateway_token(secret):
                self.gw.audit.append("webdav.token_refused", None, None, {"source": source, "via": "basic"})
            if self.failures.failed(source):
                self.gw.audit.append("auth.backoff", None, None, {"source": source, "via": "webdav",
                                                                  "backoff_s": self.settings.auth_backoff_s})
            return challenge
        role = self.passwords.role_of(row.person_id)
        if role not in CREATE_ROLES:  # the person left, or is now a guest or child: the password stops working
            self.gw.audit.append("webdav.refused", {"id": row.person_id, "kind": "person", "role": role}, None,
                                 {"app_password": row.id, "reason": "role"})
            return challenge
        now = self.gw.clock()
        if row.last_used_at is None or (now - row.last_used_at.replace(tzinfo=UTC)).total_seconds() > 60:
            self.passwords.repo.touch(row.id, now)
        return Principal(id=row.person_id, kind="person", role=role), row

    # ---- the request --------------------------------------------------------------------------
    async def handle(self, scope, receive) -> Response:
        headers = Headers(scope=scope)
        if not self.settings.enabled or not self.reaches(scope, headers):
            return text(404, "Not Found")
        source = (scope.get("client") or ("unknown",))[0]
        if (left := self.failures.blocked_for(source)) > 0:
            return text(429, "Too many wrong passwords from this address.", {"Retry-After": str(int(left) + 1)})
        who = self.authenticate(headers, source)
        if isinstance(who, Response):
            return who
        p, row = who
        if (wait := self.buckets.take(row.id)) > 0:
            return text(429, "Too many requests.", {"Retry-After": str(int(wait) + 1)})
        method = scope["method"].upper()
        try:
            handler = getattr(self, "do_" + method, None) if method in ALLOW.split(", ") else None
            if handler is None:
                raise DavError(405, f"{method} is not supported", {"Allow": ALLOW})
            place = self.resolve(scope["path"], p, row)
            return await handler(place, p, row, headers, receive)
        except DavError as e:
            return text(e.status, e.message, e.headers)
        except FilesError as e:
            status = {413: 507, 422: 400}.get(e.status, e.status)
            return text(status, e.message)

    def resolve(self, path: str, p: Principal, row: AppPasswordRow) -> Place:
        rest = path[len(PREFIX):].strip("/")
        if not rest:
            return Place(None, None)
        name, _, tail = rest.partition("/")
        kind = SPACES.get(name)
        if kind is None or kind not in row.scope_map():
            raise DavError(404, "no such space")
        return Place(kind, f"home:{p.id}" if kind == "home" else "shared", paths.split_path(tail))

    def writable(self, place: Place, p: Principal, row: AppPasswordRow) -> None:
        if place.kind is None or not place.parts:
            raise DavError(403, "a space itself cannot be changed")
        if row.scope_map()[place.kind] != "rw":
            raise DavError(403, "this app password is read-only here")
        if place.parts[0] == CLOUD_DIR:
            raise DavError(403, "Cloud folders are imports and read-only; change them at the source")
        self.files.target(p, place.root, place.path, "entry")

    async def drain(self, receive, limit: int = SMALL_BODY) -> int:
        size = 0
        while True:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return size
            size += len(msg.get("body", b""))
            if size > limit:
                raise DavError(413, "request body too large")
            if not msg.get("more_body", False):
                return size

    # ---- reading ------------------------------------------------------------------------------
    def _stat(self, place: Place, p: Principal) -> os.stat_result:
        t = self.files.target(p, place.root, place.path, "read")
        with self.files._space(t.root) as space:
            if not t.parts:
                return os.fstat(space)
            with paths.dir_at(space, t.parts[:-1]) as d:
                return paths.lstat_at(d, t.parts[-1])

    def _children(self, place: Place, p: Principal) -> Iterator[tuple[str, os.stat_result]]:
        t = self.files.target(p, place.root, place.path, "read")
        with self.files._space(t.root) as space, paths.dir_at(space, t.parts) as d, os.scandir(d) as it:
            for e in it:
                if not paths.is_utf8(e.name):
                    continue
                try:
                    yield e.name, e.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue

    @staticmethod
    def _response(href: str, name: str, st: os.stat_result | None) -> str:
        kind = paths.kind_of(st) if st else "dir"
        props = [f"<D:displayname>{escape(name)}</D:displayname>"]
        if kind == "dir":
            props.append("<D:resourcetype><D:collection/></D:resourcetype>")
        else:
            props += ["<D:resourcetype/>", f"<D:getcontentlength>{st.st_size}</D:getcontentlength>",
                      f"<D:getcontenttype>{escape(guess_mime(name))}</D:getcontenttype>"]
        if st:
            props += [f"<D:getlastmodified>{http_date(st.st_mtime)}</D:getlastmodified>",
                      f"<D:creationdate>{datetime.fromtimestamp(st.st_mtime, UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}</D:creationdate>",
                      f'<D:getetag>"{st.st_mtime_ns:x}-{st.st_size:x}"</D:getetag>']
        props.append("<D:supportedlock><D:lockentry><D:lockscope><D:exclusive/></D:lockscope>"
                     "<D:locktype><D:write/></D:locktype></D:lockentry></D:supportedlock><D:lockdiscovery/>")
        return (f"<D:response><D:href>{escape(href)}</D:href><D:propstat><D:prop>{''.join(props)}</D:prop>"
                "<D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>")

    def _propfind(self, place: Place, p: Principal, row: AppPasswordRow, depth: str) -> str:
        out: list[str] = []
        if place.kind is None:
            out.append(self._response(PREFIX + "/", "OneMind", None))
            if depth == "1":
                for kind in sorted(row.scope_map()):
                    child = Place(kind, f"home:{p.id}" if kind == "home" else "shared")
                    try:
                        out.append(self._response(child.href(True), NAMES[kind], self._stat(child, p)))
                    except FilesError:
                        continue  # the role no longer reaches this space
            return "".join(out)
        st = self._stat(place, p)
        kind = paths.kind_of(st)
        if kind not in ("dir", "file"):
            raise denied("WebDAV never follows a symbolic link", "symlink")
        out.append(self._response(place.href(kind == "dir"), place.parts[-1] if place.parts else NAMES[place.kind], st))
        if kind == "dir" and depth == "1":
            for name, cst in self._children(place, p):
                if paths.kind_of(cst) in ("dir", "file"):
                    child = Place(place.kind, place.root, place.parts + (name,))
                    out.append(self._response(child.href(paths.kind_of(cst) == "dir"), name, cst))
        return "".join(out)

    async def do_OPTIONS(self, place, p, row, headers, receive) -> Response:
        return Response(status_code=200, headers={"DAV": "1, 2", "Allow": ALLOW, "MS-Author-Via": "DAV"})

    async def do_PROPFIND(self, place, p, row, headers, receive) -> Response:
        await self.drain(receive)
        depth = headers.get("depth", "1").strip().lower()
        if depth not in ("0", "1"):
            body = '<?xml version="1.0" encoding="utf-8"?><D:error xmlns:D="DAV:"><D:propfind-finite-depth/></D:error>'
            return Response(body, status_code=403, media_type="application/xml; charset=utf-8")
        inner = await asyncio.to_thread(self._propfind, place, p, row, depth)
        body = f'<?xml version="1.0" encoding="utf-8"?>\n<D:multistatus xmlns:D="DAV:">{inner}</D:multistatus>'
        return Response(body, status_code=207, media_type="application/xml; charset=utf-8")

    async def do_GET(self, place, p, row, headers, receive, head: bool = False) -> Response:
        if place.kind is None or not place.parts:
            raise DavError(405, "a folder has no content; open it in a WebDAV client", {"Allow": ALLOW})
        t = self.files.target(p, place.root, place.path, "read")

        def open_it():
            with self.files._space(t.root) as space, paths.dir_at(space, t.parts[:-1]) as d:
                return paths.open_file_at(d, t.parts[-1])

        try:
            fd, st = await asyncio.to_thread(open_it)
        except FilesError as e:
            if e.reason == "not_a_file":
                raise DavError(405, "a folder has no content", {"Allow": ALLOW}) from None
            raise
        start, end, status = 0, st.st_size - 1, 200
        info = {"Content-Type": guess_mime(t.parts[-1]), "Last-Modified": http_date(st.st_mtime),
                "ETag": f'"{st.st_mtime_ns:x}-{st.st_size:x}"', "Accept-Ranges": "bytes"}
        rng = headers.get("range", "")
        if rng.startswith("bytes=") and "," not in rng and st.st_size:
            a, _, b = rng[6:].strip().partition("-")
            try:
                start, end = (int(a), min(int(b), end) if b else end) if a else (max(0, st.st_size - int(b)), end)
            except ValueError:
                start, end = 0, -1
            if not 0 <= start <= end:
                os.close(fd)
                return text(416, "range not satisfiable", {"Content-Range": f"bytes */{st.st_size}"})
            status, info["Content-Range"] = 206, f"bytes {start}-{end}/{st.st_size}"
        info["Content-Length"] = str(end - start + 1)
        if head:
            os.close(fd)
            return Response(status_code=status, headers=info)

        async def chunks():
            try:
                pos = start
                while pos <= end:
                    data = await asyncio.to_thread(os.pread, fd, min(CHUNK, end - pos + 1), pos)
                    if not data:
                        break
                    pos += len(data)
                    yield data
            finally:
                os.close(fd)

        return StreamingResponse(chunks(), status_code=status, headers=info)

    async def do_HEAD(self, place, p, row, headers, receive) -> Response:
        return await self.do_GET(place, p, row, headers, receive, head=True)

    # ---- writing ------------------------------------------------------------------------------
    def _place_file(self, p: Principal, place: Place, part: str, size: int, sha256: str) -> bool:
        """Move a finished part file into place (the old file goes to the Trash). True when it replaced one."""
        root = self.files.target(p, place.root, place.path, "entry").root
        self.files.check_space(root, size)
        with self.files._lock, self.files._space(root) as space, paths.dir_at(space, place.parts[:-1]) as d:
            existed = paths.exists_at(d, place.parts[-1])
            if existed:
                kind = paths.kind_of(paths.lstat_at(d, place.parts[-1]))
                if kind == "symlink":
                    raise denied("WebDAV never writes through a symbolic link", "symlink")
                if kind != "file":
                    raise DavError(405, "a folder cannot be replaced by a file")
                self.files.trash(p, place.root, place.path, index=False)
            with self.files._system("webdav") as up:
                os.rename(part, place.parts[-1], src_dir_fd=up, dst_dir_fd=d)
            os.fsync(d)
        self.files.reindex(root, place.parts, depth=0, known_hash="sha256:" + sha256)
        self.files.event("written", p, {"root": root.id, "path": place.path, "size": size, "sha256": sha256, "via": "webdav"})
        return existed

    def _new_part(self) -> tuple[str, int]:
        name = new_id("dav") + ".part"
        with self.files._system("webdav") as up:
            return name, os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=up)

    def _drop_part(self, name: str) -> None:
        try:
            with self.files._system("webdav") as up:
                os.unlink(name, dir_fd=up)
        except (OSError, FilesError):
            pass

    async def do_PUT(self, place, p, row, headers, receive) -> Response:
        self.writable(place, p, row)
        cap = self.files.settings.upload_max_bytes
        expected = headers.get("content-length") or headers.get("x-expected-entity-length")
        expected_n = int(expected) if expected and expected.isascii() and expected.isdigit() else None
        if expected_n is not None and expected_n > cap:
            raise DavError(413, f"files over {cap} bytes are not accepted")
        with self.files._space(self.files.target(p, place.root, place.path, "entry").root) as space:
            try:
                os.close(paths.open_dir(space, place.parts[:-1]))
            except FilesError:
                raise DavError(409, "the folder to put this file in does not exist") from None
        if expected_n:
            self.files.check_space(self.files.target(p, place.root, place.path, "entry").root, expected_n)
        part, fd = await asyncio.to_thread(self._new_part)
        size, h, done = 0, hashlib.sha256(), False
        try:
            try:
                while True:
                    msg = await receive()
                    if msg["type"] == "http.disconnect":
                        raise DavError(400, "the client went away")
                    data = msg.get("body", b"")
                    size += len(data)
                    if size > cap:
                        raise DavError(413, f"files over {cap} bytes are not accepted")
                    if data:
                        h.update(data)
                        await asyncio.to_thread(os.write, fd, data)
                    if not msg.get("more_body", False):
                        break
                await asyncio.to_thread(os.fsync, fd)
            finally:
                os.close(fd)
            existed = await asyncio.to_thread(self._place_file, p, place, part, size, h.hexdigest())
            done = True
        finally:
            if not done:
                await asyncio.to_thread(self._drop_part, part)
        return Response(status_code=204 if existed else 201)

    async def do_MKCOL(self, place, p, row, headers, receive) -> Response:
        if await self.drain(receive):
            raise DavError(415, "MKCOL takes no body")
        self.writable(place, p, row)
        try:
            await asyncio.to_thread(self.files.mkdir, p, place.root, place.path)
        except FilesError as e:
            if e.reason == "exists":
                raise DavError(405, "it already exists") from None
            if e.status == 404:
                raise DavError(409, "the parent folder does not exist") from None
            raise
        return Response(status_code=201)

    async def do_DELETE(self, place, p, row, headers, receive) -> Response:
        self.writable(place, p, row)
        await asyncio.to_thread(self.files.trash, p, place.root, place.path)
        return Response(status_code=204)

    def destination(self, headers: Headers, p: Principal, row: AppPasswordRow) -> Place:
        raw = headers.get("destination", "")
        target = unquote(urlsplit(raw).path)
        if not raw or not is_dav_path(target):
            raise DavError(400, "Destination must be a path under /dav/")
        return self.resolve(target, p, row)

    def _copy_or_move(self, src: Place, dst: Place, p: Principal, overwrite: bool, copy: bool) -> bool:
        if dst.root == src.root and paths.is_within(dst.parts, src.parts):
            raise conflict("a folder cannot go inside itself", "into_itself")
        st = self._stat(src, p)
        with self.files._space(self.files.target(p, dst.root, dst.path, "entry").root) as space:
            with paths.dir_at(space, dst.parts[:-1]) as d:
                existed = paths.exists_at(d, dst.parts[-1])
        if existed and not overwrite:
            raise DavError(412, "the destination exists and Overwrite is F")
        if not copy:
            if existed:
                self.files.trash(p, dst.root, dst.path)
            self.files.move(p, src.root, src.path, dst.root, dst.path)
            return existed
        if paths.kind_of(st) != "file":
            raise DavError(403, "copy folders in the Files app; WebDAV copies files")
        t = self.files.target(p, src.root, src.path, "read")
        with self.files._space(t.root) as space, paths.dir_at(space, t.parts[:-1]) as d:
            sfd, sst = paths.open_file_at(d, t.parts[-1])
        part, fd = self._new_part()
        try:
            h = hashlib.sha256()
            while data := os.read(sfd, CHUNK):
                h.update(data)
                os.write(fd, data)
            os.fsync(fd)
            os.close(fd)
            fd = -1
            return self._place_file(p, dst, part, sst.st_size, h.hexdigest())
        except BaseException:
            self._drop_part(part)
            raise
        finally:
            os.close(sfd)
            if fd >= 0:
                os.close(fd)

    async def do_MOVE(self, place, p, row, headers, receive, copy: bool = False) -> Response:
        if not copy:
            self.writable(place, p, row)
        dst = self.destination(headers, p, row)
        self.writable(dst, p, row)
        overwrite = headers.get("overwrite", "T").strip().upper() != "F"
        existed = await asyncio.to_thread(self._copy_or_move, place, dst, p, overwrite, copy)
        return Response(status_code=204 if existed else 201)

    async def do_COPY(self, place, p, row, headers, receive) -> Response:
        if place.kind is None or not place.parts:
            raise DavError(403, "a space itself cannot be copied")
        return await self.do_MOVE(place, p, row, headers, receive, copy=True)

    async def do_LOCK(self, place, p, row, headers, receive) -> Response:
        await self.drain(receive)
        self.writable(place, p, row)
        token = f"opaquelocktoken:{uuid.uuid4()}"
        body = ('<?xml version="1.0" encoding="utf-8"?>\n<D:prop xmlns:D="DAV:"><D:lockdiscovery><D:activelock>'
                "<D:locktype><D:write/></D:locktype><D:lockscope><D:exclusive/></D:lockscope><D:depth>0</D:depth>"
                f"<D:timeout>Second-3600</D:timeout><D:locktoken><D:href>{token}</D:href></D:locktoken>"
                f"<D:lockroot><D:href>{escape(place.href(False))}</D:href></D:lockroot>"
                "</D:activelock></D:lockdiscovery></D:prop>")
        return Response(body, status_code=200, media_type="application/xml; charset=utf-8",
                        headers={"Lock-Token": f"<{token}>"})

    async def do_UNLOCK(self, place, p, row, headers, receive) -> Response:
        return Response(status_code=204)


class WebDavMiddleware:
    """Answers /dav and /dav/... before the guard; every other request passes straight through."""

    def __init__(self, app, dav: WebDav):
        self.app, self.dav = app, dav
        self.headers = [(k, v) for k, v in SECURITY_HEADERS if k != b"content-security-policy"]
        self.headers.append((b"content-security-policy", CSP.encode()))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not is_dav_path(scope.get("path", "")):
            return await self.app(scope, receive, send)
        try:
            response = await self.dav.handle(scope, receive)
        except Exception:  # noqa: BLE001 - a client must get an answer; the detail goes to the log
            log.exception("webdav %s failed", scope.get("method"))
            response = text(500, "internal error")
        response.raw_headers.extend(self.headers)
        await response(scope, receive, send)
