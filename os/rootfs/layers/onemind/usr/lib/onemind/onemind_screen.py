# SPDX-License-Identifier: Apache-2.0
"""The box's own screen (UX-07, #242): what a monitor on the box shows instead of a login prompt.

Setup address and a QR code of it, the role, and whether OneMind is ready. Nothing secret is ever drawn:
the owner token is shown once on the setup page (onemind_setup.py), never here. Read-only: it only reads
files and asks the local gateway or the setup wizard for /healthz. Run by onemind-screen.service on tty1.

It also shows the box confirmation code (D-028, N-1 b): a 6-digit code the gateway writes to
/data/onemind/gateway/box-code.json when an L2 approval needs a person standing at the box. It is good
once, for 2 minutes, and no network API ever returns it; reading it here is the proof of presence.

The QR encoder is here too (byte mode, error level L or M, versions 1-6: up to 134 bytes), so the image
needs no QR package. It follows ISO/IEC 18004; test/unit/test_screen.py pins its output and the PR notes
how it was checked with a real decoder.
"""
import json, os, socket, subprocess, sys, time, urllib.request

PORT = 8080
BOX_CODE = ("data", "onemind", "gateway", "box-code.json")  # written by the gateway (identity/presence.py)

# ------------------------------------------------------------------ QR code
# version -> (data codewords total, ec codewords per block, blocks) for levels L and M.
_EC = {
    "L": {1: (19, 7, 1), 2: (34, 10, 1), 3: (55, 15, 1), 4: (80, 20, 1), 5: (108, 26, 1), 6: (136, 18, 2)},
    "M": {1: (16, 10, 1), 2: (28, 16, 1), 3: (44, 26, 1), 4: (64, 18, 2), 5: (86, 24, 2), 6: (112, 16, 4)},
}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34]}
_LEVEL_BITS = {"L": 1, "M": 0}
_EXP, _LOG = [0] * 512, [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i], _LOG[_x] = _x, _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gmul(a, b):
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _rs(data, n):
    """Reed-Solomon remainder: n error-correction codewords for `data`."""
    gen = [1]
    for i in range(n):
        nxt = [0] * (len(gen) + 1)
        for j, c in enumerate(gen):
            nxt[j] ^= c
            nxt[j + 1] ^= _gmul(c, _EXP[i])
        gen = nxt
    rem = [0] * n
    for b in data:
        f = b ^ rem[0]
        rem = rem[1:] + [0]
        for i in range(n):
            rem[i] ^= _gmul(gen[i + 1], f)
    return rem


def _codewords(payload, version, level):
    total, ecn, blocks = _EC[level][version]
    bits = "0100" + format(len(payload), "08b") + "".join(format(b, "08b") for b in payload)
    bits += "0" * min(4, total * 8 - len(bits))
    bits += "0" * (-len(bits) % 8)
    cw = [int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)]
    pad = [0xEC, 0x11]
    while len(cw) < total:
        cw.append(pad[(len(cw) - len(bits) // 8) % 2])
    size = total // blocks
    data = [cw[i * size:(i + 1) * size] for i in range(blocks)]
    ec = [_rs(d, ecn) for d in data]
    out = [d[i] for i in range(size) for d in data] + [e[i] for i in range(ecn) for e in ec]
    return out


def _bch(value, poly, bits_total, shift):
    v = value << shift
    for i in range(bits_total - 1, shift - 1, -1):
        if v >> i & 1:
            v ^= poly << (i - shift)
    return (value << shift) | v


_MASKS = [lambda r, c: (r + c) % 2 == 0, lambda r, c: r % 2 == 0, lambda r, c: c % 3 == 0,
          lambda r, c: (r + c) % 3 == 0, lambda r, c: (r // 2 + c // 3) % 2 == 0,
          lambda r, c: r * c % 2 + r * c % 3 == 0, lambda r, c: (r * c % 2 + r * c % 3) % 2 == 0,
          lambda r, c: ((r + c) % 2 + r * c % 3) % 2 == 0]


def _penalty(m):
    n, score = len(m), 0
    for grid in (m, [list(col) for col in zip(*m)]):
        for row in grid:
            run = 1
            for i in range(1, n):
                if row[i] == row[i - 1]:
                    run += 1
                    continue
                score += run - 2 if run >= 5 else 0
                run = 1
            score += run - 2 if run >= 5 else 0
            s = "".join("1" if x else "0" for x in row)
            score += 40 * (s.count("10111010000") + s.count("00001011101"))
    for r in range(n - 1):
        for c in range(n - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                score += 3
    dark = sum(map(sum, m))
    score += 10 * (abs(dark * 20 - n * n * 10) // (n * n))
    return score


def qr_matrix(text, level="M"):
    """The QR code of `text` as a list of rows of 0/1 (1 = dark), without the quiet zone."""
    payload = text.encode("utf-8")
    for version in range(1, 7):
        if len(payload) <= _EC[level][version][0] - 2:
            break
    else:
        raise ValueError("text too long for the screen's QR code (134 bytes at most)")
    n = 17 + 4 * version
    mod = [[0] * n for _ in range(n)]
    fn = [[False] * n for _ in range(n)]

    def put(r, c, v, func=True):
        mod[r][c] = int(v)
        if func:
            fn[r][c] = True

    for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):                     # finder patterns and separators
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = r0 + dr, c0 + dc
                if 0 <= r < n and 0 <= c < n:
                    ring = max(abs(dr - 3), abs(dc - 3))
                    put(r, c, 0 <= dr <= 6 and 0 <= dc <= 6 and ring != 2)
    for i in range(8, n - 8):                                            # timing
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)
    pos = _ALIGN[version]
    for r in pos:                                                        # alignment
        for c in pos:
            if fn[r][c]:
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    put(r + dr, c + dc, max(abs(dr), abs(dc)) != 1)
    for i in range(9):                                                   # reserve the format areas
        fn[8][i] = fn[i][8] = True                                       # first copy: 9 + 9 cells around the top-left finder
        if i < 8:
            fn[8][n - 1 - i] = fn[n - 1 - i][8] = True                   # second copy: 8 + 8 cells (the dark module is one)
    put(n - 8, 8, 1)                                                     # the always-dark module
    cw = _codewords(payload, version, level)
    bits = [b >> (7 - i) & 1 for b in cw for i in range(8)]
    k, up = 0, True
    right = n - 1
    while right >= 1:                                                    # data, zigzag in column pairs
        if right == 6:                                                   # skip the vertical timing column
            right = 5
        for v in range(n):
            r = n - 1 - v if up else v
            for c in (right, right - 1):
                if not fn[r][c] and k < len(bits):
                    mod[r][c] = bits[k]
                    k += 1
        up = not up
        right -= 2
    best = None
    for mask in range(8):
        m = [row[:] for row in mod]
        for r in range(n):
            for c in range(n):
                if not fn[r][c] and _MASKS[mask](r, c):
                    m[r][c] ^= 1
        fmt = _bch(_LEVEL_BITS[level] << 3 | mask, 0x537, 15, 10) ^ 0x5412
        for i in range(15):                                              # format bits, both copies (row, column)
            b = fmt >> i & 1
            r1, c1 = (i, 8) if i < 6 else (7, 8) if i == 6 else (8, 8) if i == 7 else (8, 7) if i == 8 else (8, 14 - i)
            r2, c2 = (8, n - 1 - i) if i < 8 else (n - 15 + i, 8)
            m[r1][c1] = m[r2][c2] = b
        m[n - 8][8] = 1                                                  # the always-dark module
        score = _penalty(m)
        if best is None or score < best[0]:
            best = (score, m)
    return best[1]


def qr_lines(text, level="M", quiet=2):
    """The code as terminal lines: black modules on a white background, two rows of modules per line."""
    m = qr_matrix(text, level)
    n = len(m) + 2 * quiet
    g = [[0] * n for _ in range(n)]
    for r, row in enumerate(m):
        for c, v in enumerate(row):
            g[r + quiet][c + quiet] = v
    if n % 2:
        g.append([0] * n)
    out = []
    for r in range(0, len(g), 2):
        out.append("\x1b[30;47m" + "".join(" ▀▄█"[g[r][c] | g[r + 1][c] << 1] for c in range(n)) + "\x1b[0m")
    return out


# ------------------------------------------------------------------ what the box knows
def addresses():
    """IPv4 addresses a person on the same network could use: not loopback, not the cluster's own links."""
    try:
        out = subprocess.run(["ip", "-j", "-4", "addr", "show", "scope", "global"], capture_output=True, text=True, timeout=5).stdout
        links = json.loads(out)
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    skip = ("cni", "flannel", "veth", "docker", "kube", "cali", "tailscale", "ts", "br-", "virbr", "lxc")
    return [a["local"] for link in links if not link.get("ifname", "").startswith(skip)
            for a in link.get("addr_info", []) if a.get("family") == "inet"]


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status, r.read(200).decode("utf-8", "replace")
    except (OSError, ValueError):
        return None, ""


def gather(root="/"):
    j = lambda *p: os.path.join(root, *p)
    state = None
    try:
        with open(j("data", "onemind", "firstboot", "state.json")) as f:
            state = json.load(f)
    except (OSError, ValueError):
        pass
    tls = False
    try:
        with open(j("data", "onemind", "etc", "gateway.env")) as f:
            tls = any(line.strip() == "ONEMIND_NET_TLS=1" for line in f)
    except OSError:
        pass
    # Health is always probed on loopback: with TLS on, plain HTTP :8080 is bound to loopback only (H-05).
    status, body = _get(f"http://127.0.0.1:{PORT}/healthz")
    code = None
    if status == 200 and body.strip() == "setup":
        try:
            with open(j("run", "onemind", "setup-code")) as f:
                code = f.read().strip() or None
        except OSError:
            pass
    box = None
    try:
        with open(j(*BOX_CODE)) as f:
            doc = json.load(f)
        if str(doc.get("code", "")).isdigit() and int(doc.get("expires_at", 0)) > time.time():
            box = {"code": str(doc["code"]), "what": str(doc.get("what") or "")[:120]}
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {"tls": tls, "setup_code": code, "box_code": box, "host": socket.gethostname(), "addrs": addresses(),
            "role": state.get("role") if isinstance(state, dict) else None,
            "name": state.get("name") if isinstance(state, dict) else None,
            "setup_open": status == 200 and body.strip() == "setup",
            "ready": status == 200 and body.strip() != "setup"}


def view(info):
    """(headline, lines, url or None) for the facts in `info`. A pure function: the tests call it."""
    addr = info["addrs"][0] if info["addrs"] else None
    role = info.get("role")
    setup = info["setup_open"] or (role is None and not info["ready"])
    # Plain HTTP :8080 is only the setup wizard. Once set up on a hub (ONEMIND_NET_TLS=1, H-05) the gateway
    # serves the LAN over HTTPS on :443 and :8080 is loopback only, so the screen must never point at it.
    https = not setup and (info.get("tls") or role == "hub")
    if https:
        url = f"https://{addr}/" if addr else None
        names = f"https://{info['host']}.local/  /  https://onemind.local/"
    else:
        url = f"http://{addr}:{PORT}/" if addr else None
        names = f"http://{info['host']}.local:{PORT}/  /  http://onemind.local:{PORT}/"
    if setup:
        head = "FINISH SETUP"
        lines = ["On a phone or computer on the same network, open:", "",
                 f"   {url}" if url else "   (no network yet: plug in the network cable)",
                 f"   or {names}", "",
                 *([f"Setup code (the page asks for it): {info['setup_code']}", ""] if info.get("setup_code") else []),
                 "Choose what this box is. The page then shows your owner token ONCE:",
                 "copy it. It is never shown on this screen."]
    elif role in ("worker", "leaf"):
        head = f"ONEMIND {role.upper()}" if info["ready"] else "ONEMIND IS STARTING"
        lines = [f"This box is a {role} of a OneMind hub.", "", "Manage it from the hub's dashboard."]
        url = None
    elif info["ready"]:
        head = "ONEMIND IS RUNNING"
        lines = ["Open the dashboard on a phone or computer on this network:", "",
                 f"   {url}" if url else "   (no network address yet)",
                 f"   or {names}", "",
                 "Sign in with your owner token (shown once when you set this box up)."]
    else:
        head = "ONEMIND IS STARTING"
        lines = ["The first start takes a few minutes.", "",
                 f"The address will be: {url}" if url else "Waiting for a network address."]
    box = info.get("box_code")
    if box:  # a person at the box confirms an approval or a change that needs a proven key (N-1 b)
        code = box["code"]
        head = "CONFIRM AT THE BOX"
        lines = [f"Code:  {code[:3]} {code[3:]}", "", f"For: {box['what']}" if box.get("what") else "",
                 "Type it where OneMind asks for it. It works once, for 2 minutes.",
                 "Didn't ask for this? Ignore it: nothing happens without the code.", "", *lines]
    return head, lines, url


def render(info, width=80):
    head, lines, url = view(info)
    out = ["\x1b[2J\x1b[H", "", f"  \x1b[1m{head}\x1b[0m   ({info['name'] or info['host']})", ""]
    out += ["  " + line for line in lines]
    if url:
        out += [""] + ["  " + row for row in qr_lines(url)]
    out += ["", "  OneMind OS. Development build screens may differ."]
    return "\n".join(out) + "\n"


def main():
    last = None
    with open(os.environ.get("ONEMIND_SCREEN_TTY", "/dev/tty1"), "w") as tty:
        while True:
            text = render(gather())
            if text != last:
                tty.write(text)
                tty.flush()
                last = text
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
