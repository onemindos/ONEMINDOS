#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""UMB-ACCT-1 lab client: talks to Kanidm v1.12.0 over its HTTPS JSON API.

It holds a software passkey (a virtual WebAuthn authenticator: P-256 key, "none" attestation,
user-presence and user-verification flags set), runs the credential-update, sign-in, OIDC
auth-code + PKCE and TOTP flows, and prints one JSON line per step. It never prints a
password, token, TOTP secret or private key: those live in AK_SECRETS (mode 0700) only.

Only the Python standard library and python3-cryptography (Debian 13 package) are used.
"""
import base64
import hashlib
import hmac
import json
import os
import ssl
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

BASE = os.environ.get("AK_URL", "https://idm.onemind.test:8443")
CA = os.environ.get("AK_CA", "/etc/kanidm/ca.pem")
SECRETS = os.environ.get("AK_SECRETS", "/root/aklab/secrets")
SESSION_HDR = "X-KANIDM-AUTH-SESSION-ID"


def out(**kw):
    print(json.dumps(kw, sort_keys=True), flush=True)


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64(s):
    s = s.replace("+", "-").replace("/", "_")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def secret_path(name):
    os.makedirs(SECRETS, mode=0o700, exist_ok=True)
    return os.path.join(SECRETS, name)


def read_secret(name):
    with open(secret_path(name)) as f:
        return f.read().strip()


def write_secret(name, value):
    p = secret_path(name)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def http(method, path, body=None, headers=None, form=None):
    ctx = ssl.create_default_context(cafile=CA)
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), _NoRedirect)
    h = {"Accept": "application/json"}
    h.update(headers or {})
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        r = opener.open(req, timeout=60)
        return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def bearer(tok):
    return {"Authorization": "Bearer " + tok}


# ---------------------------------------------------------------- CBOR (only what WebAuthn needs)
def cbor(v):
    def head(major, n):
        if n < 24:
            return bytes([major << 5 | n])
        if n < 256:
            return bytes([major << 5 | 24, n])
        if n < 65536:
            return bytes([major << 5 | 25]) + n.to_bytes(2, "big")
        return bytes([major << 5 | 26]) + n.to_bytes(4, "big")

    if isinstance(v, int):
        return head(0, v) if v >= 0 else head(1, -1 - v)
    if isinstance(v, bytes):
        return head(2, len(v)) + v
    if isinstance(v, str):
        b = v.encode()
        return head(3, len(b)) + b
    if isinstance(v, dict):
        return head(5, len(v)) + b"".join(cbor(k) + cbor(x) for k, x in v.items())
    raise TypeError(type(v))


# ---------------------------------------------------------------- software passkey
class SoftPasskey:
    """A virtual authenticator whose key lives in AK_SECRETS/<name>.passkey.json."""

    def __init__(self, name):
        self.name = name + ".passkey.json"

    def _load(self):
        return json.loads(read_secret(self.name))

    def _save(self, d):
        write_secret(self.name, json.dumps(d))

    def exists(self):
        return os.path.exists(secret_path(self.name))

    @staticmethod
    def _client_data(kind, challenge, origin):
        return json.dumps({"type": kind, "challenge": b64u(unb64(challenge)), "origin": origin,
                           "crossOrigin": False}, separators=(",", ":")).encode()

    def create(self, ccr, origin):
        pk = ccr["publicKey"]
        rp_id = pk["rp"]["id"]
        key = ec.generate_private_key(ec.SECP256R1())
        cred_id = os.urandom(32)
        nums = key.public_key().public_numbers()
        cose = cbor({1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")})
        flags = 0x01 | 0x04 | 0x40  # UP, UV, AT
        auth_data = (hashlib.sha256(rp_id.encode()).digest() + bytes([flags]) + struct.pack(">I", 0)
                     + b"\x00" * 16 + struct.pack(">H", len(cred_id)) + cred_id + cose)
        cd = self._client_data("webauthn.create", pk["challenge"], origin)
        att = cbor({"fmt": "none", "attStmt": {}, "authData": auth_data})
        self._save({"rp_id": rp_id, "cred_id": b64u(cred_id), "user_handle": pk["user"]["id"],
                    "count": 0, "key_pem": key.private_bytes(serialization.Encoding.PEM,
                                                             serialization.PrivateFormat.PKCS8,
                                                             serialization.NoEncryption()).decode()})
        return {"id": b64u(cred_id), "rawId": b64u(cred_id), "type": "public-key", "extensions": {},
                "response": {"attestationObject": b64u(att), "clientDataJSON": b64u(cd)}}

    def get(self, rcr, origin):
        d = self._load()
        pk = rcr["publicKey"]
        rp_id = pk.get("rpId") or d["rp_id"]
        allowed = [c["id"] for c in pk.get("allowCredentials") or []]
        if allowed and d["cred_id"] not in [b64u(unb64(a)) for a in allowed]:
            raise RuntimeError("server did not offer this passkey's credential id")
        d["count"] += 1
        auth_data = hashlib.sha256(rp_id.encode()).digest() + bytes([0x01 | 0x04]) + struct.pack(">I", d["count"])
        cd = self._client_data("webauthn.get", pk["challenge"], origin)
        key = serialization.load_pem_private_key(d["key_pem"].encode(), None)
        sig = key.sign(auth_data + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256()))
        self._save(d)
        return {"id": d["cred_id"], "rawId": d["cred_id"], "type": "public-key", "extensions": {},
                "response": {"authenticatorData": b64u(auth_data), "clientDataJSON": b64u(cd),
                             "signature": b64u(sig), "userHandle": d["user_handle"]}}

    def fingerprint(self):
        """A public id for the evidence: sha256 of the credential id (not secret)."""
        return hashlib.sha256(unb64(self._load()["cred_id"])).hexdigest()[:16]


# ---------------------------------------------------------------- TOTP
def totp_code(secret_bytes, algo, step, digits, t=None):
    counter = int((t if t is not None else time.time()) // step)
    dig = {"sha1": hashlib.sha1, "sha256": hashlib.sha256, "sha512": hashlib.sha512}[algo.lower()]
    mac = hmac.new(secret_bytes, struct.pack(">Q", counter), dig).digest()
    o = mac[-1] & 0x0F
    return (struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** digits), counter


def fresh_totp(name):
    """Like a person with an authenticator app: never type a code from a time step already used."""
    t = json.loads(read_secret(name))
    last = max(t.get("enrol_counter", -1), t.get("last_counter", -1))
    while int(time.time() // t["step"]) <= last:
        time.sleep(0.5)
    code, ctr = totp_code(bytes(t["secret"]), t["algo"], t["step"], t["digits"])
    t["last_counter"] = ctr
    write_secret(name, json.dumps(t))
    return code


# ---------------------------------------------------------------- sign-in
def origin():
    return BASE


def signin(username, mech, totp_name=None, totp_code_override=None):
    """Returns (ok, detail, token). Never prints the token."""
    st, h, b = http("POST", "/v1/auth", {"step": {"init2": {"username": username, "issue": "token",
                                                              "privileged": False}}})
    if st != 200:
        return False, "init http %s %s" % (st, b[:200].decode(errors="replace")), None
    sid = h.get(SESSION_HDR)
    state = json.loads(b)["state"]
    if "choose" not in state:
        return False, "init state %s" % json.dumps(state)[:200], None
    offered = state["choose"]
    if mech not in offered:
        return False, "mech %s not offered (offered %s)" % (mech, offered), None
    hdr = {SESSION_HDR: sid}
    st, h, b = http("POST", "/v1/auth", {"step": {"begin": mech}}, hdr)
    state = json.loads(b)["state"] if st == 200 else {"http": st}
    used_code = None
    for _ in range(4):
        if "success" in state:
            return True, "success (mech %s)" % mech, state["success"]
        if "denied" in state:
            return False, "denied: %s" % state["denied"], None
        if "continue" not in state:
            return False, "state %s" % json.dumps(state)[:200], None
        allowed = state["continue"]
        cred = None
        for a in allowed:
            if isinstance(a, dict) and "passkey" in a:
                cred = {"passkey": SoftPasskey(username).get(a["passkey"], origin())}
            elif a == "totp":
                if totp_code_override is not None:
                    used_code = totp_code_override
                else:
                    used_code = fresh_totp(totp_name)
                cred = {"totp": used_code}
            elif a == "password":
                cred = {"password": read_secret(username + ".password")}
            if cred:
                break
        if cred is None:
            return False, "cannot satisfy %s" % allowed, None
        st, h, b = http("POST", "/v1/auth", {"step": {"cred": cred}}, hdr)
        if st != 200:
            return False, "cred http %s %s" % (st, b[:200].decode(errors="replace")), None
        state = json.loads(b)["state"]
    return False, "too many steps", None


# ---------------------------------------------------------------- credential update
def cu_exchange(intent_token):
    st, _, b = http("POST", "/v1/credential/_exchange_intent", intent_token)
    if st != 200:
        return None, st, b[:300].decode(errors="replace")
    sess, status = json.loads(b)
    return sess, st, status


def cu_update(sess, req):
    st, _, b = http("POST", "/v1/credential/_update", [req, sess])
    return st, (json.loads(b) if st == 200 else b[:300].decode(errors="replace"))


def cu_commit(sess):
    st, _, b = http("POST", "/v1/credential/_commit", sess)
    return st, b[:200].decode(errors="replace")


def summarize(status):
    if not isinstance(status, dict):
        return status
    reg = status.get("mfaregstate")
    return {"can_commit": status.get("can_commit"), "warnings": status.get("warnings"),
            "primary": (status.get("primary") or {}).get("type") if status.get("primary") else None,
            "passkeys": [p.get("tag") for p in status.get("passkeys", [])],
            "mfaregstate": reg if isinstance(reg, str) else list(reg)[0]}


def enrol(username, intent_name, what):
    """Use a reset token (from AK_SECRETS/<intent_name>) to enrol: passkey, password, password+totp."""
    sess, st, status = cu_exchange(read_secret(intent_name))
    if sess is None:
        out(step="exchange_intent", user=username, ok=False, http=st, body=status)
        return False
    out(step="exchange_intent", user=username, ok=True, status=summarize(status))
    if "password" in what:
        pw = b64u(os.urandom(24))
        st, status = cu_update(sess, {"password": pw})
        ok = st == 200
        if ok:
            write_secret(username + ".password", pw)
        out(step="set_password", user=username, ok=ok, status=summarize(status))
        if not ok:
            return False
    if "totp" in what:
        st, status = cu_update(sess, "totpgenerate")
        ts = status["mfaregstate"]["TotpCheck"]
        if ts["algo"] != "sha1":
            pass
        code, ctr = totp_code(bytes(ts["secret"]), ts["algo"], ts["step"], ts["digits"])
        st, status = cu_update(sess, {"totpverify": [code, "lab-totp"]})
        if isinstance(status, dict) and status.get("mfaregstate") == "TotpInvalidSha1":
            st, status = cu_update(sess, "totpacceptsha1")
        write_secret(username + ".totp", json.dumps({"secret": ts["secret"], "algo": ts["algo"],
                                                     "step": ts["step"], "digits": ts["digits"],
                                                     "enrol_counter": ctr}))
        out(step="totp_enrol", user=username, ok=st == 200, algo=ts["algo"], step_s=ts["step"],
            digits=ts["digits"], status=summarize(status))
    if "passkey" in what:
        st, status = cu_update(sess, "passkeyinit")
        if st != 200 or "Passkey" not in status.get("mfaregstate", {}):
            out(step="passkey_init", user=username, ok=False, http=st, status=summarize(status))
            return False
        ccr = status["mfaregstate"]["Passkey"]
        sel = ccr["publicKey"].get("authenticatorSelection")
        out(step="passkey_init", user=username, ok=True, rp_id=ccr["publicKey"]["rp"]["id"],
            user_verification=(sel or {}).get("userVerification"),
            attestation=ccr["publicKey"].get("attestation"))
        cred = SoftPasskey(username).create(ccr, origin())
        st, status = cu_update(sess, {"passkeyfinish": ["lab-virtual-authenticator", cred]})
        out(step="passkey_finish", user=username, ok=st == 200 and bool(status.get("passkeys")),
            http=st, status=summarize(status), credential_fp=SoftPasskey(username).fingerprint())
    st, body = cu_commit(sess)
    out(step="commit", user=username, ok=st == 200, http=st)
    return st == 200


def reuse_intent(intent_name):
    sess, st, body = cu_exchange(read_secret(intent_name))
    out(step="reuse_reset_token", ok=sess is None, refused=sess is None, http=st,
        body=body if sess is None else "accepted")
    if sess is not None:
        http("POST", "/v1/credential/_cancel", sess)
    return sess is None


# ---------------------------------------------------------------- OIDC
def oidc(username, client, redirect, mech="password", scope="openid groups"):
    ok, detail, tok = signin(username, mech)
    if not ok:
        out(step="oidc_idp_signin", user=username, ok=False, detail=detail)
        return {"refused_at": "idp_signin", "detail": detail}
    verifier = b64u(os.urandom(32))
    challenge = b64u(hashlib.sha256(verifier.encode()).digest())
    state, nonce = b64u(os.urandom(12)), b64u(os.urandom(12))
    req = {"response_type": "code", "client_id": client, "state": state, "code_challenge": challenge,
           "code_challenge_method": "S256", "redirect_uri": redirect, "scope": scope,
           "nonce": nonce}
    st, h, b = http("POST", "/oauth2/authorise", req, bearer(tok))
    out(step="oidc_authorise", user=username, http=st, requested_scope=scope)
    if st != 200:
        return {"refused_at": "authorise", "http": st}
    j = json.loads(b) if b else None
    loc = h.get("Location")
    if isinstance(j, dict) and "ConsentRequested" in j:
        cr = j["ConsentRequested"]
        out(step="oidc_consent_requested", user=username, scopes=sorted(cr.get("scopes", [])))
        st, h, b = http("POST", "/oauth2/authorise/permit", cr["consent_token"], bearer(tok))
        out(step="oidc_permit", user=username, http=st)
        loc = h.get("Location")
    if not loc:
        return {"refused_at": "no_redirect", "http": st}
    q = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
    if q.get("state", [None])[0] != state or "code" not in q:
        return {"refused_at": "redirect", "error": q.get("error")}
    secret = read_secret(client + ".client_secret")
    basic = base64.b64encode((client + ":" + secret).encode()).decode()
    st, h, b = http("POST", "/oauth2/token", headers={"Authorization": "Basic " + basic},
                    form={"grant_type": "authorization_code", "code": q["code"][0],
                          "redirect_uri": redirect, "code_verifier": verifier, "client_id": client})
    out(step="oidc_token", user=username, http=st)
    if st != 200:
        return {"refused_at": "token", "http": st, "body": b[:200].decode(errors="replace")}
    tr = json.loads(b)
    idt = tr["id_token"]
    hdr_b, pay_b, sig_b = idt.split(".")
    header, claims = json.loads(unb64(hdr_b)), json.loads(unb64(pay_b))
    verified = verify_jws(client, header, (hdr_b + "." + pay_b).encode(), unb64(sig_b))
    keep = {k: claims.get(k) for k in ("iss", "aud", "preferred_username", "onemind_role", "email",
                                        "name", "nonce") if k in claims}
    keep["groups_onemind"] = sorted(g for g in claims.get("groups", []) if g.startswith("onemind_"))
    keep["nonce_matches"] = claims.get("nonce") == nonce
    keep.pop("nonce", None)
    keep["scope"] = tr.get("scope")
    keep["signature_verified"] = verified
    keep["alg"] = header.get("alg")
    return {"id_token_claims": keep}


def verify_jws(client, header, signing_input, sig):
    st, _, b = http("GET", "/oauth2/openid/%s/public_key.jwk" % client)
    if st != 200 or header.get("alg") != "ES256":
        return False
    for k in json.loads(b).get("keys", []):
        if header.get("kid") and k.get("kid") != header["kid"]:
            continue
        pub = ec.EllipticCurvePublicNumbers(int.from_bytes(unb64(k["x"]), "big"),
                                            int.from_bytes(unb64(k["y"]), "big"),
                                            ec.SECP256R1()).public_key()
        der = encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"))
        try:
            pub.verify(der, signing_input, ec.ECDSA(hashes.SHA256()))
            return True
        except Exception:
            return False
    return False


# ---------------------------------------------------------------- commands
def main(argv):
    cmd = argv[0]
    if cmd == "enrol":  # enrol <user> <intent-secret-name> <passkey|password|password+totp>
        return 0 if enrol(argv[1], argv[2], argv[3].split("+")) else 1
    if cmd == "reuse-intent":
        return 0 if reuse_intent(argv[1]) else 1
    if cmd == "signin":  # signin <user> <mech> [expect=ok|refused]
        ok, detail, tok = signin(argv[1], argv[2], totp_name=argv[1] + ".totp")
        who = None
        if ok:
            st, _, b = http("GET", "/v1/self", headers=bearer(tok))
            who = (json.loads(b)["youare"]["attrs"].get("spn", ["?"])[0]) if st == 200 else "self http %s" % st
            write_secret(argv[1] + ".uat", tok)
        out(step="signin", user=argv[1], mech=argv[2], ok=ok, detail=detail, whoami=who)
        expect = argv[3] if len(argv) > 3 else "ok"
        return 0 if ok == (expect == "ok") else 1
    if cmd == "session-check":  # session-check <user>: is the earlier session token still accepted?
        tok = read_secret(argv[1] + ".uat")
        st1, _, _ = http("GET", "/v1/self", headers=bearer(tok))
        st2, _, b2 = http("GET", "/v1/auth/valid", headers=bearer(tok))
        out(step="session_check", user=argv[1], self_http=st1, auth_valid_http=st2)
        return 0
    if cmd == "oidc":  # oidc <user> <client> <redirect> [mech]
        r = oidc(argv[1], argv[2], argv[3], argv[4] if len(argv) > 4 else "password",
                 argv[5] if len(argv) > 5 else "openid groups")
        out(step="oidc_result", user=argv[1], result=r)
        return 0
    if cmd == "totp-replay":  # totp-replay <user>
        t = json.loads(read_secret(argv[1] + ".totp"))
        step = t["step"]
        # start at the beginning of a fresh time step, later than the enrolment step
        while True:
            now = time.time()
            ctr = int(now // step)
            if ctr > t["enrol_counter"] and (now % step) < step / 3:
                break
            time.sleep(0.5)
        code, ctr = totp_code(bytes(t["secret"]), t["algo"], step, t["digits"])
        ok1, d1, _ = signin(argv[1], "passwordmfa", totp_code_override=code)
        ok2, d2, _ = signin(argv[1], "passwordmfa", totp_code_override=code)
        same_step = int(time.time() // step) == ctr
        out(step="totp_replay", user=argv[1], first_ok=ok1, first=d1, second_ok=ok2, second=d2,
            same_time_step=same_step, algo=t["algo"], step_s=step)
        return 0 if ok1 and not ok2 and same_step else 1
    if cmd == "memberof":  # memberof <api-token-secret-name> <user...>
        tok = read_secret(argv[1])
        rc = 0
        for u in argv[2:]:
            st, _, b = http("GET", "/v1/person/%s/_attr/memberof" % u, headers=bearer(tok))
            groups = sorted(g.split("@")[0] for g in json.loads(b)) if st == 200 and b != b"null" else None
            onemind = [g for g in (groups or []) if g.startswith("onemind_")]
            out(step="memberof", user=u, http=st, onemind_groups=onemind)
            rc |= 0 if onemind else 1
        return rc
    if cmd == "passkey-fp":
        out(step="passkey_fp", user=argv[1], credential_fp=SoftPasskey(argv[1]).fingerprint())
        return 0
    print("unknown command", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
