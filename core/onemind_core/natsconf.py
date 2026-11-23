# SPDX-License-Identifier: Apache-2.0
"""Hub NATS accounts: one account per joined node (H-06; NETWORKING.md §7; contract §12.9).

Why accounts and not users with permissions: the FB-3 lab (research-output/evidence/lab/
fb3-mesh-nat, E2) showed nats-server v2.15.2 refuses `permissions` on leaf users, and a leaf in a
shared account could publish as any other node. With one account per node the isolation is
structural: whatever a node's leaf publishes lands in that node's own account, and the hub account
imports only that node's own subjects from it. Node A publishing `onemind.node.B.status` stays in
A's account, where nobody listens.

Layout of the generated file (included by the hub's nats.conf; the gateway rewrites it on every
join and removal, and a systemd path unit reloads NATS):

- account ONEMIND: the hub's own clients (gateway, hub onemindd) on the loopback client port, each
  with its own service nkey (CORE-SEC-4, #161), allowed on STANDARD connections only, so a leaf can
  never fall into it. A client with no key or an unknown key is refused. Without any service key
  (the dev compose stack, a box installed before #161) the account falls back to the passwordless
  `no_auth_user` "hub-local", also STANDARD only;
- account NODE_<node_id> per node: one nkey user (the node's own public key, sent at join; the
  seed never leaves the node), allowed on LEAFNODE connections only. It exports its
  status/event/jobresult subjects to ONEMIND and imports its own job subjects from it;
- hub sourcing (#747): the hub keeps a copy of each node's leaf outbox in a source stream
  (jetstream.HubSource, internal/leaf HubSourceStream). Each NODE_<id> exports to ONEMIND only what
  that needs, in the shape of the NATS "Mirrors and sources" page (cross-account): the consumer API
  of its outbox in its own JetStream domain and the flow-control replies as service exports, and the
  delivery subject as a stream export. The delivery subject sits under the node's own prefix, so a
  node can feed only its own source stream, and ONEMIND exports nothing back for it.

The file holds public keys only; no secret is written.
"""

from __future__ import annotations

import base64
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

HUB_ACCOUNT = "ONEMIND"
HUB_LOCAL_USER = "hub-local"
NODE_ID_RE = re.compile(r"^[a-z0-9]{1,32}$")
_B32 = re.compile(r"^[A-Z2-7]+$")

SERVICE_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")

# Subjects a node publishes (contract §12.9), relative to onemind.node.<node_id>.
NODE_EXPORTS = ("status", "event.>", "jobresult.>")
# Subjects the hub sends to one node.
NODE_IMPORTS = ("job.>",)

# Hub sourcing of a leaf's outbox (#747). OUTBOX_STREAM is internal/leaf OutboxStream; a node's leaf
# runs JetStream in the domain node-<node_id> (internal/leaf Config.Domain).
OUTBOX_STREAM = "OUTBOX"


def node_domain(node_id: str) -> str:
    """The JetStream domain of a node's leaf."""
    return f"node-{node_id}"


def node_js_api(node_id: str) -> str:
    """The prefix under which the hub reaches the JetStream API of a node's leaf, over the leaf link."""
    return f"$JS.{node_domain(node_id)}.API"


def source_deliver_prefix(node_id: str) -> str:
    """Where a node's leaf delivers its outbox to the hub's source stream: under the node's own prefix."""
    return f"onemind.node.{node_id}.outbox"


def source_services(node_id: str) -> tuple[str, ...]:
    """The service subjects the hub's source stream needs in a node's account: create and delete its
    consumer on the outbox (nats-server v2.15.3 stream.go setupSourceConsumer, tryDeleteSourcingConsumer:
    CONSUMER.CREATE.<stream> plain or extended, CONSUMER.DELETE.<stream>.<consumer>) and answer flow
    control (consumer.go: $JS.FC.<stream>.<consumer>.<n>).

    Known gap: a leaf names its flow-control subject without its domain (the v1 format; v2 needs the
    leaf's js_ack_fc_v2 feature flag), so every node account imports the same $JS.FC.OUTBOX.> and the
    hub's empty flow-control replies (two sequence counters, no event) reach every node. Follow-up on
    #747: turn the flag on in internal/leaf's leaf.conf, then import $JS.FC.node-<id>.> per node."""
    api = node_js_api(node_id)
    return (f"{api}.CONSUMER.CREATE.{OUTBOX_STREAM}", f"{api}.CONSUMER.CREATE.{OUTBOX_STREAM}.>",
            f"{api}.CONSUMER.DELETE.{OUTBOX_STREAM}.>", f"$JS.FC.{OUTBOX_STREAM}.>")


def _crc16(data: bytes) -> int:
    """CRC-16/XMODEM, the checksum nkeys appends to every encoded key."""
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def is_user_public_nkey(value: str) -> bool:
    """True for a well-formed NATS *user* public nkey (prefix U, 56 base32 chars, valid CRC)."""
    if not isinstance(value, str) or len(value) != 56 or not value.startswith("U") or not _B32.match(value):
        return False
    try:
        raw = base64.b32decode(value)  # 56 characters = 35 bytes, no padding
    except ValueError:
        return False
    if len(raw) != 35 or raw[0] != 20 << 3:  # nkeys.PrefixByteUser
        return False
    return _crc16(raw[:-2]) == int.from_bytes(raw[-2:], "little")


@dataclass(frozen=True)
class NodeAccount:
    node_id: str
    nkey: str  # the node's user public nkey

    def __post_init__(self):
        if not NODE_ID_RE.match(self.node_id):
            raise ValueError(f"node id {self.node_id!r} is not a lowercase id")
        if not is_user_public_nkey(self.nkey):
            raise ValueError(f"node {self.node_id}: not a NATS user public nkey")

    @property
    def account(self) -> str:
        return f"NODE_{self.node_id}"


@dataclass(frozen=True)
class ServiceKey:
    """A hub-local service (gateway, onemindd) and its user public nkey (CORE-SEC-4, #161)."""
    name: str
    nkey: str

    def __post_init__(self):
        if not SERVICE_RE.match(self.name):
            raise ValueError(f"service name {self.name!r} is not a lowercase name")
        if not is_user_public_nkey(self.nkey):
            raise ValueError(f"service {self.name}: not a NATS user public nkey")


# What the hub account may keep in JetStream: file storage only (no memory store: a restart must not
# lose events silently), capped in total. App streams are carved out of this (streams.py).
JETSTREAM_MAX_STREAMS = 32
JETSTREAM_MAX_CONSUMERS = 128


def render_accounts(nodes: Iterable[NodeAccount], services: Iterable[ServiceKey] = (),
                    jetstream_max_bytes: int = 0) -> str:
    """The accounts include file. Deterministic: same nodes and services, same bytes (no reload churn).

    jetstream_max_bytes > 0 turns JetStream on for the hub account with that file-storage cap. Node
    accounts never get JetStream: a leaf's events are kept by its own outbox and by the hub account."""
    nodes = sorted({n.node_id: n for n in nodes}.values(), key=lambda n: n.node_id)
    services = sorted({s.name: s for s in services}.values(), key=lambda s: s.name)
    if services:  # strict: every hub-local client signs with its own key
        hub_users = [f'      {{nkey: "{s.nkey}", allowed_connection_types: ["STANDARD"]}}  # {s.name}'
                     for s in services]
    else:  # no service keys: the passwordless loopback user (see the module docstring)
        hub_users = [f'      {{user: "{HUB_LOCAL_USER}", allowed_connection_types: ["STANDARD"]}}']
    out = [
        "# Generated by the OneMind gateway (core/onemind_core/natsconf.py). Do not edit: rewritten on",
        "# every node join and removal. Public keys only. One account per node (H-06, FB-3 lab E2).",
        "accounts {",
        f"  {HUB_ACCOUNT}: {{",
        "    users: [",
        *hub_users,
        "    ]",
    ]
    if jetstream_max_bytes > 0:
        out.append(f"    jetstream: {{max_mem: 0, max_file: {int(jetstream_max_bytes)}, "
                   f"max_streams: {JETSTREAM_MAX_STREAMS}, max_consumers: {JETSTREAM_MAX_CONSUMERS}}}")
    imports = []
    for n in nodes:
        imports += [f'      {{stream: {{account: "{n.account}", subject: "onemind.node.{n.node_id}.{s}"}}}}'
                    for s in NODE_EXPORTS]
        imports += [f'      {{service: {{account: "{n.account}", subject: "{s}"}}}}' for s in source_services(n.node_id)]
        imports.append(f'      {{stream: {{account: "{n.account}", subject: "{source_deliver_prefix(n.node_id)}.>"}}}}')
    exports = [
        f'      {{stream: "onemind.node.{n.node_id}.{s}", accounts: ["{n.account}"]}}'
        for n in nodes for s in NODE_IMPORTS
    ]
    out += ["    imports: [", *imports, "    ]"] if imports else []
    out += ["    exports: [", *exports, "    ]"] if exports else []
    out.append("  }")
    for n in nodes:
        out += [
            f"  {n.account}: {{",
            f'    users: [{{nkey: "{n.nkey}", allowed_connection_types: ["LEAFNODE"]}}]',
            "    exports: [",
            *[f'      {{stream: "onemind.node.{n.node_id}.{s}", accounts: ["{HUB_ACCOUNT}"]}}' for s in NODE_EXPORTS],
            *[f'      {{service: "{s}", accounts: ["{HUB_ACCOUNT}"]}}' for s in source_services(n.node_id)],
            f'      {{stream: "{source_deliver_prefix(n.node_id)}.>", accounts: ["{HUB_ACCOUNT}"]}}',
            "    ]",
            "    imports: [",
            *[f'      {{stream: {{account: "{HUB_ACCOUNT}", subject: "onemind.node.{n.node_id}.{s}"}}}}'
              for s in NODE_IMPORTS],
            "    ]",
            "  }",
        ]
    out.append("}")
    if not services:
        out.append(f'no_auth_user: "{HUB_LOCAL_USER}"')
    out.append("")
    return "\n".join(out)


def load_service_keys(directory: Path | None) -> list[ServiceKey]:
    """Every `<service>.pub` in `directory` (ONEMIND_FABRIC_NATS_SERVICE_KEYS). A bad file raises:
    silently skipping it would lock that service out of NATS."""
    if directory is None or not directory.is_dir():
        return []
    return [ServiceKey(p.stem, p.read_text(encoding="ascii").strip()) for p in sorted(directory.glob("*.pub"))]


def _encode(prefix: bytes, payload: bytes) -> str:
    raw = prefix + payload
    return base64.b32encode(raw + _crc16(raw).to_bytes(2, "little")).decode().rstrip("=")


def new_user_key() -> tuple[str, str]:
    """A fresh NATS user nkey pair as (seed "SU...", public "U..."), in the nkeys encoding (Ed25519,
    base32, CRC-16), made with `cryptography`. The seed is a secret; the public key is not."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    user, seed_type = 20 << 3, 18 << 3  # nkeys PrefixByteUser, PrefixByteSeed
    seed_prefix = bytes([seed_type | (user >> 5), (user & 31) << 3])
    return _encode(seed_prefix, seed), _encode(bytes([user]), pub)


def load_seed(path: Path):
    """Read a user nkey seed file: returns (public key "U...", sign(bytes) -> 64-byte Ed25519
    signature). With `cryptography`, not the `nkeys` package, which has no wheel for the image's
    --only-binary install (#269)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    text = Path(path).read_text(encoding="ascii").strip()
    try:
        raw = base64.b32decode(text + "=" * (-len(text) % 8))
    except ValueError:
        raw = b""
    user = 20 << 3
    if (len(raw) != 36 or _crc16(raw[:-2]) != int.from_bytes(raw[-2:], "little")
            or raw[0] != (18 << 3 | user >> 5) or raw[1] != (user & 31) << 3):
        raise ValueError(f"{path} is not a NATS user nkey seed")
    key = Ed25519PrivateKey.from_private_bytes(raw[2:34])
    pub = _encode(bytes([user]), key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
    return pub, key.sign


def make_service_key(directory: Path, name: str) -> str:
    """Write `<name>.nk` (seed, 0600) and `<name>.pub` (0644) once; keep an existing pair.
    Returns the public key. The installer then hands the seed file to the service's user."""
    if not SERVICE_RE.match(name):
        raise ValueError(f"service name {name!r} is not a lowercase name")
    directory.mkdir(parents=True, exist_ok=True)
    seed_file, pub_file = directory / f"{name}.nk", directory / f"{name}.pub"
    if seed_file.exists() and pub_file.exists():
        return pub_file.read_text(encoding="ascii").strip()
    seed, pub = new_user_key()
    fd = os.open(seed_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (seed + "\n").encode())
    finally:
        os.close(fd)
    os.chmod(seed_file, 0o600)
    pub_file.write_text(pub + "\n", encoding="ascii")
    os.chmod(pub_file, 0o644)
    return pub


def write_accounts(path: Path, nodes: Iterable[NodeAccount], services: Iterable[ServiceKey] = (),
                   jetstream_max_bytes: int = 0) -> bool:
    """Write the include file atomically (0644: public keys only). True if the content changed."""
    body = render_accounts(nodes, services, jetstream_max_bytes).encode()
    try:
        if path.read_bytes() == body:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, body)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)  # a rename, so the systemd path unit sees one change and NATS never half a file
    return True


USAGE = """usage: python -m onemind_core.natsconf ACCOUNTS_FILE [SERVICE_KEYS_DIR]
       python -m onemind_core.natsconf service-key SERVICE_KEYS_DIR NAME"""


def main(argv: list[str] | None = None) -> int:
    """The installer's steps on the hub. `service-key DIR NAME` makes a service's nkey pair (kept if
    it exists) and prints the public key. `ACCOUNTS_FILE [DIR]` writes the first accounts file (hub
    account, plus the service keys in DIR) before the hub NATS first starts; an existing file is
    left alone, and the gateway rewrites it from the ledger and DIR when it starts."""
    import sys

    args = sys.argv[1:] if argv is None else argv
    if len(args) == 3 and args[0] == "service-key":
        print(make_service_key(Path(args[1]), args[2]))
        return 0
    if len(args) not in (1, 2) or args[0] == "service-key":
        print(USAGE, file=sys.stderr)
        return 2
    path = Path(args[0])
    if not path.exists():
        write_accounts(path, [], load_service_keys(Path(args[1])) if len(args) == 2 else [],
                       int(os.environ.get("ONEMIND_FABRIC_JETSTREAM_MAX_BYTES") or 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
