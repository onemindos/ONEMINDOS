// SPDX-License-Identifier: Apache-2.0
// The shared join QR vectors (FABRIC §4.2): Python and Go run the same file, so all three parsers agree.
import { describe, expect, it } from "vitest";
import { JOIN_KINDS, JoinQRError, parseJoinQR } from "../src/index.js";

/* eslint-disable @typescript-eslint/no-explicit-any */
interface Vectors {
  reasons: string[];
  valid: { name: string; payload: string; expect: Record<string, unknown> }[];
  hostile: { name: string; payload: string; reason: string }[];
}

async function vectors(): Promise<Vectors> {
  const spec = "node:" + "fs"; // not a literal: the package keeps "types": [] (no @types/node)
  const fs: any = await import(/* @vite-ignore */ spec);
  return JSON.parse(fs.readFileSync(new URL("../../testdata/join-qr/vectors.json", import.meta.url), "utf8"));
}

describe("parseJoinQR", () => {
  it("accepts every valid vector with exactly the expected fields", async () => {
    const v = await vectors();
    expect(v.valid.length).toBeGreaterThanOrEqual(10);
    for (const c of v.valid) expect(parseJoinQR(c.payload), c.name).toEqual(c.expect);
  });

  it("refuses every hostile vector with the same reason as Python and Go", async () => {
    const v = await vectors();
    expect(v.hostile.length).toBeGreaterThanOrEqual(50);
    for (const c of v.hostile) {
      let err: unknown;
      try {
        parseJoinQR(c.payload);
      } catch (e) {
        err = e;
      }
      expect(err, c.name).toBeInstanceOf(JoinQRError);
      expect((err as JoinQRError).reason, c.name).toBe(c.reason);
      expect(v.reasons).toContain(c.reason);
    }
  });

  it("names the same kinds as the gateway", () => {
    expect([...JOIN_KINDS]).toEqual(["worker", "leaf", "phone", "desktop", "browser", "sensor"]);
  });
});
