#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""MeshCore companion link check (#853): a passive, read-only talk with a radio flashed Companion (USB).

It sends only APP_START, DEVICE_QUERY and GET_STATS. The encoder below cannot build any other command, so it
cannot make the radio transmit, advertise or change a radio setting. Frame layouts: MeshCore
docs/companion_protocol.md (MIT) and meshcore_py 2.3.19 reader.py (MIT) for the STATS reply.

  python3 -I link_check.py run --port /dev/ttyUSB0 --out DIR [--idle-seconds 600]
  python3 -I link_check.py decode DIR/captured-frames.json     # re-decode saved frames, exit 1 on a mismatch

Python standard library only (termios), so nothing is installed on the hub.
"""
import argparse, datetime, json, os, select, struct, sys, time

# The allowlist: opcode -> name. Nothing else can be framed (see frame()).
ALLOWED_COMMANDS = {0x01: "APP_START", 0x16: "DEVICE_QUERY", 0x38: "GET_STATS"}
STATS_TYPES = {"core": 0, "packets": 2}
APP_NAME = b"onemind-linkcheck"
MAX_FRAME = 300  # meshcore_py drops frames longer than this

# Fixed test values written in place of the radio's identity before anything is saved.
TEST_PUBLIC_KEY = bytes(range(0xA0, 0xC0))
TEST_NAME = "OneMind Test Radio"
TEST_PIN = 123456

US_BAND_MHZ = (902.0, 928.0)
M2_MAX_DBM = 19  # FCC ID 2BDNA-CL06: 0.08123 W conducted, about 19.1 dBm


class RefusedCommand(ValueError):
    """The kit refused to frame a command outside its read-only allowlist."""


def app_start():
    return bytes([0x01]) + bytes(7) + APP_NAME


def device_query():
    return bytes([0x16, 0x03])


def get_stats(kind):
    return bytes([0x38, STATS_TYPES[kind]])


def frame(payload):
    """Wrap an app-to-radio payload as `<` + uint16 LE length + payload, only if it is on the allowlist."""
    payload = bytes(payload)
    ok = (payload == device_query()
          or payload == app_start()
          or (len(payload) == 2 and payload[0] == 0x38 and payload[1] in STATS_TYPES.values()))
    if not ok:
        raise RefusedCommand("refused command %s: the link check only reads" % payload[:1].hex())
    return b"<" + struct.pack("<H", len(payload)) + payload


class Deframer:
    """Split the radio-to-app byte stream (`>` + uint16 LE length + payload) into payloads."""

    def __init__(self):
        self.buf = b""

    def feed(self, data):
        self.buf += data
        out = []
        while True:
            start = self.buf.find(b">")
            if start < 0:
                self.buf = b""
                return out
            self.buf = self.buf[start:]
            if len(self.buf) < 3:
                return out
            n = struct.unpack("<H", self.buf[1:3])[0]
            if n == 0 or n > MAX_FRAME:
                self.buf = self.buf[1:]
                continue
            if len(self.buf) < 3 + n:
                return out
            out.append(self.buf[3:3 + n])
            self.buf = self.buf[3 + n:]


def _text(b):
    return b.split(b"\0", 1)[0].decode("utf-8", "replace").strip()


def decode(p):
    """Decode one radio-to-app payload into named fields (physical units). Raises ValueError if short."""
    p = bytes(p)
    if not p:
        raise ValueError("empty frame")
    code = p[0]
    if code == 0x05:  # SELF_INFO
        if len(p) < 58:
            raise ValueError("SELF_INFO too short: %d bytes" % len(p))
        lat, lon = struct.unpack("<ii", p[36:44])
        freq, bw = struct.unpack("<II", p[48:56])
        return {"kind": "SELF_INFO", "adv_type": p[1], "tx_power_dbm": p[2], "max_tx_power_dbm": p[3],
                "public_key": p[4:36].hex(), "lat": lat / 1e6, "lon": lon / 1e6,
                "freq_mhz": freq / 1000.0, "bw_khz": bw / 1000.0, "sf": p[56], "cr": p[57],
                "name": p[58:].decode("utf-8", "replace").rstrip("\0").strip()}
    if code == 0x0D:  # DEVICE_INFO
        if len(p) < 2:
            raise ValueError("DEVICE_INFO too short")
        out = {"kind": "DEVICE_INFO", "fw_ver": p[1]}
        if p[1] >= 3:
            if len(p) < 80:
                raise ValueError("DEVICE_INFO too short for fw_ver %d: %d bytes" % (p[1], len(p)))
            out.update(max_contacts=p[2] * 2, max_channels=p[3], ble_pin=struct.unpack("<I", p[4:8])[0],
                       fw_build=_text(p[8:20]), model=_text(p[20:60]), version=_text(p[60:80]))
        if p[1] >= 9 and len(p) > 80:
            out["client_repeat"] = p[80] != 0
        if p[1] >= 10 and len(p) > 81:
            out["path_hash_mode"] = p[81]
        return out
    if code == 0x18:  # STATS
        if len(p) < 2:
            raise ValueError("STATS too short")
        if p[1] == 0:
            if len(p) < 11:
                raise ValueError("STATS core too short")
            mv, up, err, q = struct.unpack("<HIHB", p[2:11])
            return {"kind": "STATS_CORE", "battery_mv": mv, "uptime_s": up, "errors": err, "queue_len": q}
        if p[1] == 2:
            if len(p) < 26:
                raise ValueError("STATS packets too short")
            keys = ("recv", "sent", "flood_tx", "direct_tx", "flood_rx", "direct_rx")
            out = dict(kind="STATS_PACKETS", **dict(zip(keys, struct.unpack("<6I", p[2:26]))))
            out["recv_errors"] = struct.unpack("<I", p[26:30])[0] if len(p) >= 30 else None
            return out
        return {"kind": "STATS_UNKNOWN", "stats_type": p[1]}
    if code == 0x01:  # ERROR
        return {"kind": "ERROR", "error_code": p[1] if len(p) > 1 else None}
    return {"kind": "UNKNOWN", "code": code}


def redact(p):
    """Replace the radio's public key, name, advert location and BLE PIN with fixed test values."""
    p = bytes(p)
    if p[:1] == b"\x05" and len(p) >= 58:
        return p[:4] + TEST_PUBLIC_KEY + bytes(8) + p[44:58] + TEST_NAME.encode()
    if p[:1] == b"\x0d" and len(p) >= 8 and p[1] >= 3:
        return p[:4] + struct.pack("<I", TEST_PIN) + p[8:]
    return p


def preset_report(si):
    """Read-only check that the owner set the US preset and power in MeshCore's own client."""
    reasons = []
    lo, hi = si["freq_mhz"] - si["bw_khz"] / 2000.0, si["freq_mhz"] + si["bw_khz"] / 2000.0
    if lo < US_BAND_MHZ[0] or hi > US_BAND_MHZ[1]:
        reasons.append("channel %.4f-%.4f MHz is outside the US 902-928 MHz band" % (lo, hi))
    if si["tx_power_dbm"] > M2_MAX_DBM:
        reasons.append("transmit power %d dBm is above 19 dBm (the M2's FCC grant)" % si["tx_power_dbm"])
    return {"state": "fails" if reasons else "works", "reasons": reasons}


def no_transmit_verdict(reads):
    """reads: [{label, core: {uptime_s} | None, packets: {sent, flood_tx, direct_tx} | None}] in time order."""
    labels = [r["label"] for r in reads]
    if labels != ["before", "after", "idle"] or any(not r.get("packets") or not r.get("core") for r in reads):
        return {"state": "partial", "reason": "not every GET_STATS read answered (have %s)" % ", ".join(
            r["label"] for r in reads if r.get("packets") and r.get("core"))}
    up = [r["core"]["uptime_s"] for r in reads]
    if any(b < a for a, b in zip(up, up[1:])):
        return {"state": "partial", "reason": "the radio restarted during the check (uptime %s), so its "
                "counters reset; run it again" % up}
    tx = [(r["packets"]["sent"], r["packets"]["flood_tx"], r["packets"]["direct_tx"]) for r in reads]
    if any(b != a for a, b in zip(tx, tx[1:])):
        return {"state": "fails", "reason": "the sent count rose: (sent, flood_tx, direct_tx) %s" % tx}
    return {"state": "works", "reason": "sent count stayed at %d across before, after and idle" % tx[0][0]}


class Radio:
    """A raw 115200-baud serial link. Writes only go through frame(), so only allowlisted commands leave."""

    def __init__(self, port, timeout):
        import termios
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(self.fd)
        attrs[0] = 0  # iflag: no translation
        attrs[1] = 0  # oflag
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # no HUPCL: closing does not drop DTR
        attrs[3] = 0  # lflag: raw
        attrs[4] = attrs[5] = termios.B115200
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        termios.tcflush(self.fd, termios.TCIOFLUSH)
        self.timeout, self.deframer, self.pending = timeout, Deframer(), []
        self.sent_log, self.push = [], {}

    def close(self):
        os.close(self.fd)

    def write(self, payload):
        data = frame(payload)
        self.sent_log.append(payload[:1].hex())
        os.write(self.fd, data)

    def read_frames(self, seconds):
        end = time.monotonic() + seconds
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return
            r, _, _ = select.select([self.fd], [], [], left)
            if r:
                try:
                    data = os.read(self.fd, 512)
                except BlockingIOError:
                    continue
                for p in self.deframer.feed(data):
                    if p[0] >= 0x80:  # push frames are counted, never stored (adverts carry other people's keys)
                        key = "0x%02x" % p[0]
                        self.push[key] = self.push.get(key, 0) + 1
                    else:
                        self.pending.append(p)

    def command(self, payload, expect):
        """Send one allowlisted command and return the first reply whose code is in `expect` (or ERROR)."""
        self.write(payload)
        end = time.monotonic() + self.timeout
        while time.monotonic() < end:
            while self.pending:
                p = self.pending.pop(0)
                if p[0] in expect or p[0] == 0x01:
                    return p
            self.read_frames(min(0.1, max(0.0, end - time.monotonic())))
        return None


def _stats(radio, label, frames):
    read = {"label": label, "core": None, "packets": None}
    for kind in ("core", "packets"):
        p = radio.command(get_stats(kind), {0x18})
        if p is None:
            continue
        frames.append(("stats_%s_%s" % (kind, label), p))
        d = decode(p)
        if d["kind"] == "STATS_" + kind.upper():
            read[kind] = {k: v for k, v in d.items() if k != "kind"}
    return read


def run(port, out_dir, idle_seconds=600, timeout=5.0, wake_seconds=10.0):
    """The passive check. Writes report.json and captured-frames.json (redacted) into out_dir."""
    os.makedirs(out_dir, exist_ok=True)
    radio = Radio(port, timeout)
    frames, reads, checks = [], [], {}
    try:
        # Opening the port can restart an ESP32 board: wait for the first answer before counting anything.
        end = time.monotonic() + wake_seconds
        while time.monotonic() < end and radio.command(get_stats("core"), {0x18}) is None:
            pass
        radio.pending.clear()
        reads.append(_stats(radio, "before", frames))
        si = radio.command(app_start(), {0x05})
        di = radio.command(device_query(), {0x0D})
        for name, p in (("self_info", si), ("device_info", di)):
            if p is not None:
                frames.append((name, p))
        si_d = decode(si) if si is not None and si[0] == 0x05 else None
        di_d = decode(di) if di is not None and di[0] == 0x0D else None
        checks["handshake"] = {"state": "works" if si_d and di_d else ("partial" if si_d or di_d else "fails"),
                               "self_info": bool(si_d), "device_info": bool(di_d)}
        reads.append(_stats(radio, "after", frames))
        radio.read_frames(idle_seconds)  # idle: listen only, never answer
        radio.pending.clear()
        reads.append(_stats(radio, "idle", frames))
    finally:
        radio.close()
    checks["no_transmit"] = no_transmit_verdict(reads)
    checks["preset"] = preset_report(si_d) if si_d else {"state": "fails", "reasons": ["no SELF_INFO reply"]}
    radio_info = {}
    if si_d:
        radio_info.update({k: si_d[k] for k in ("freq_mhz", "bw_khz", "sf", "cr", "tx_power_dbm",
                                                 "max_tx_power_dbm")})
    if di_d:
        radio_info.update(firmware=di_d.get("version"), fw_build=di_d.get("fw_build"), model=di_d.get("model"),
                          protocol_ver=di_d.get("fw_ver"))
    when = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = {"date": when, "idle_seconds": idle_seconds, "radio": radio_info, "checks": checks,
              "stats": reads, "commands_sent": radio.sent_log, "push_frames_seen": radio.push}
    capture = {"source": "captured from a MeshCore companion radio by test/lora/link-check (#853); public key, "
                         "name, advert location and BLE PIN replaced by fixed test values", "date": when,
               "frames": []}
    for name, p in frames:
        red = redact(p)
        capture["frames"].append({"name": name, "direction": "radio-to-app", "hex": red.hex(),
                                  "decoded": decode(red)})
    with open(os.path.join(out_dir, "report.json"), "w") as f:
        json.dump(report, f, indent=2)
    with open(os.path.join(out_dir, "captured-frames.json"), "w") as f:
        json.dump(capture, f, indent=2)
    return report


def verify_capture(path):
    """Decode every saved frame again; return a list of mismatches (empty when all decode to their fields)."""
    with open(path) as f:
        doc = json.load(f)
    bad = []
    for fr in doc["frames"]:
        try:
            got = decode(bytes.fromhex(fr["hex"]))
        except ValueError as e:
            bad.append("%s: %s" % (fr["name"], e))
            continue
        if got != fr["decoded"]:
            bad.append("%s: decoded %s, file says %s" % (fr["name"], got, fr["decoded"]))
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="passive check against a radio on a serial port")
    r.add_argument("--port", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--idle-seconds", type=float, default=600)
    r.add_argument("--timeout", type=float, default=5.0)
    d = sub.add_parser("decode", help="re-decode a captured-frames.json and compare")
    d.add_argument("path")
    a = ap.parse_args(argv)
    if a.cmd == "decode":
        bad = verify_capture(a.path)
        for line in bad:
            print("MISMATCH " + line)
        print("decode: %s" % ("ok" if not bad else "%d mismatch(es)" % len(bad)))
        return 1 if bad else 0
    rep = run(a.port, a.out, a.idle_seconds, a.timeout)
    print(json.dumps({"radio": rep["radio"], "checks": rep["checks"], "push_frames_seen": rep["push_frames_seen"]},
                     indent=2))
    return 0 if all(c["state"] == "works" for c in rep["checks"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
