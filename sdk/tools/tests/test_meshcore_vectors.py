# SPDX-License-Identifier: Apache-2.0
"""Shared MeshCore test vectors (issue #855): sdk/contracts/meshcore/frames.json and guard.json.

The hub driver (#740, Go), the phone codec and guard (#865, TypeScript) and the hub guard (#857, Python) all
test against these files, so this checks the files themselves: they fit their own schema, every frame a
codec may send is on the opcode allowlist (no encoder for radio settings, power, keys or raw data), the
documented byte layouts decode to the stated fields, and every guard case is what the reference guard
below returns (Semtech time on air, US band edges, the FCC-granted power, byte caps and the budget).
"""
from __future__ import annotations

import copy
import json
import math
import struct
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

MC = Path(__file__).resolve().parents[3] / "sdk" / "contracts" / "meshcore"


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def errors(v: Draft202012Validator, obj: object) -> list[str]:
    return [e.message for e in v.iter_errors(obj)]


def ceil16(n: int) -> int:
    return -(-n // 16) * 16


def toa_ms(packet: int, sf: int, bw_khz: float, cr: int) -> int:
    """Semtech time on air: 16-symbol preamble, explicit header, CRC on; cr is the 4/x denominator."""
    tsym = (2 ** sf) * 1_000_000 // round(bw_khz * 1000)
    de = 1 if tsym >= 16000 else 0
    n = 8 + max(math.ceil((8 * packet - 4 * sf + 28 + 16) / (4 * (sf - 2 * de))) * cr, 0)
    return -(-((81 * tsym) // 4 + n * tsym) // 1000)


def reference_guard(c: dict, g: dict) -> dict:
    r, s, u, lim = c["radio"], c["send"], c["used"], g["limits"]
    grant = next((x for x in g["grants"] if x["model"] == r["model"]), None)
    lo, hi = lim["band_mhz"]
    checks = [("region_not_confirmed", not c["region_confirmed"]), ("status_stale", r["status_age_s"] > lim["status_max_age_s"]),
              ("out_of_band", r["freq_mhz"] - r["bw_khz"] / 2000 < lo or r["freq_mhz"] + r["bw_khz"] / 2000 > hi),
              ("no_grant", grant is None), ("power_over_grant", grant is not None and r["tx_power_dbm"] > grant["max_dbm"]),
              ("too_many_attempts", not 1 <= s["attempts"] <= lim["max_attempts"])]
    for reason, failed in checks:
        if failed:
            return {"ok": False, "reason": reason}
    name = len(r["name"].encode())
    nbytes = len(s.get("text", "").encode())
    if s["kind"] == "advert":
        packet = 10 + 109 + name
    else:
        cap = lim["direct_text_max_bytes"] if s["kind"] == "direct" else 160 - (name + 2)
        if nbytes == 0:
            return {"ok": False, "reason": "empty_text"}
        if nbytes > cap:
            return {"ok": False, "reason": "text_too_long", "bytes": nbytes, "max_bytes": cap}
        if s["kind"] == "channel" and s["channel_public"] and not c["public_send_enabled"]:
            return {"ok": False, "reason": "public_channel_off"}
        packet = 10 + ceil16(5 + nbytes + (0 if s["kind"] == "direct" else name + 2))
    each = toa_ms(packet, r["sf"], r["bw_khz"], r["cr"])
    out = {"bytes": nbytes, "packet_bytes": packet, "airtime_ms": each, "total_airtime_ms": each * s["attempts"]}
    if u["airtime_ms"] + out["total_airtime_ms"] > lim["budget_airtime_ms"]:
        return {"ok": False, "reason": "airtime_budget", **out}
    if u["sends"] + s["attempts"] > lim["budget_sends"]:
        return {"ok": False, "reason": "send_budget", **out}
    return {"ok": True, "reason": None, **out}


class SharedVectors(unittest.TestCase):
    frames = load(MC / "frames.json")
    guard = load(MC / "guard.json")
    v = Draft202012Validator(load(MC / "vectors.schema.json"))

    def test_the_vector_files_validate_against_their_own_schema(self):
        Draft202012Validator.check_schema(self.v.schema)
        self.assertEqual(errors(self.v, self.frames), [])
        self.assertEqual(errors(self.v, self.guard), [])
        broken = copy.deepcopy(self.guard)
        broken["cases"][0]["expect"]["ok"] = "yes"
        self.assertTrue(errors(self.v, broken))

    def test_frames_stay_on_the_allowlist_and_decode_as_documented(self):
        allow = {o["code"] for o in self.frames["allowlist"]}
        deny = {o["code"]: o["name"] for o in self.frames["deny"]}
        self.assertFalse(allow & set(deny))
        self.assertLessEqual({11, 12, 19, 23, 24, 25}, set(deny))  # radio params, power, reboot, keys, raw data
        by = {f["id"]: f for f in self.frames["frames"]}
        self.assertEqual(len(by), len(self.frames["frames"]))
        for f in self.frames["frames"]:
            raw = bytes.fromhex(f["hex"])
            if f["dir"] == "to_radio":
                self.assertIn(raw[0], allow, f["id"])
            if "serial_hex" in f:
                lead = 0x3C if f["dir"] == "to_radio" else 0x3E
                self.assertEqual(bytes.fromhex(f["serial_hex"]), bytes([lead]) + struct.pack("<H", len(raw)) + raw, f["id"])
        self.assertEqual(bytes.fromhex(by["send_self_advert_zero_hop"]["hex"])[1], 0)  # zero-hop only
        raw = bytes.fromhex(by["send_channel_txt_msg"]["hex"])
        self.assertEqual((raw[2], struct.unpack("<I", raw[3:7])[0], raw[7:].decode()), (1, 1234567890, "Hello"))
        for fid in ("self_info_us_preset", "self_info_eu_default"):
            raw, d = bytes.fromhex(by[fid]["hex"]), by[fid]["decoded"]
            freq, bw = struct.unpack("<II", raw[48:56])
            self.assertEqual((raw[2], raw[3], freq / 1000, bw / 1000, raw[56], raw[57], raw[58:].decode()),
                             (d["tx_power_dbm"], d["max_tx_power_dbm"], d["freq_mhz"], d["bw_khz"], d["sf"], d["cr"], d["name"]))
        raw = bytes.fromhex(by["device_info_m2"]["hex"])
        self.assertEqual(raw[20:60].rstrip(b"\0").decode(), by["device_info_m2"]["decoded"]["model"])
        self.assertEqual(by["device_info_m2"]["decoded"]["model"], self.guard["grants"][0]["model"])

    def test_every_guard_case_matches_the_reference_guard(self):
        self.assertEqual({c["expect"]["reason"] for c in self.guard["cases"]} - {None}, set(self.guard["reasons"]))
        for c in self.guard["cases"]:
            self.assertEqual(reference_guard(c, self.guard), c["expect"], c["id"])
        self.assertEqual(self.guard["grants"][0]["max_dbm"], 19)  # the M2's FCC grant, not its 22 dBm build default


if __name__ == "__main__":
    unittest.main()
