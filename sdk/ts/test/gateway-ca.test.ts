// SPDX-License-Identifier: Apache-2.0
// Real TLS: a throwaway CA and server certificate are made with the openssl CLI in a temp dir
// (test data only, deleted afterwards). Skipped when openssl or node:https is unavailable.
import { describe, expect, it } from "vitest";
import { OneMind } from "../src/index.js";

/* eslint-disable @typescript-eslint/no-explicit-any */
const load = (m: string): Promise<any> => import(/* @vite-ignore */ "node:" + m).catch(() => undefined);

async function pki(): Promise<{ ca: string; other: string; cert: string; key: string; cleanup: () => void } | undefined> {
  const [cp, fs, os, path] = await Promise.all(["child_process", "fs", "os", "path"].map(load));
  if (!cp || !fs) return undefined;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "om-ca-"));
  const run = (...a: string[]) => cp.execFileSync("openssl", a, { cwd: dir, stdio: "ignore" });
  try {
    const ca = (n: string) => run("req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
      "-keyout", `${n}.key`, "-out", `${n}.crt`, "-days", "1", "-subj", `/CN=onemind-sdk-test-${n}`,
      "-addext", "basicConstraints=critical,CA:TRUE");
    ca("ca"); ca("other");
    run("req", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-keyout", "srv.key",
      "-out", "srv.csr", "-subj", "/CN=gateway");
    fs.writeFileSync(path.join(dir, "ext"), "subjectAltName=IP:127.0.0.1\nextendedKeyUsage=serverAuth\n");
    run("x509", "-req", "-in", "srv.csr", "-CA", "ca.crt", "-CAkey", "ca.key", "-CAcreateserial", "-out", "srv.crt",
      "-days", "1", "-extfile", "ext");
    const rd = (f: string) => fs.readFileSync(path.join(dir, f), "utf8");
    return { ca: rd("ca.crt"), other: rd("other.crt"), cert: rd("srv.crt"), key: rd("srv.key"),
      cleanup: () => fs.rmSync(dir, { recursive: true, force: true }) };
  } catch {
    fs.rmSync(dir, { recursive: true, force: true });
    return undefined;
  }
}

describe("ONEMIND_GATEWAY_CA over real TLS", () => {
  it("verifies the gateway against that CA only", async () => {
    const https = await load("https");
    const p = await pki();
    if (!https || !p) return; // no openssl here: nothing to exercise
    const server = https.createServer({ cert: p.cert, key: p.key }, (_req: any, res: any) => {
      res.setHeader("content-type", "application/json");
      res.end('[{"node_id":"abc","status":"online","last_seen":"t"}]');
    });
    await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
    try {
      const url = `https://127.0.0.1:${server.address().port}`;
      const env = (ca?: string) => ({ ONEMIND_GATEWAY_URL: url, ONEMIND_AGENT_TOKEN: "t", ...(ca ? { ONEMIND_GATEWAY_CA: ca } : {}) });
      const quick = { retries: 1, sleep: async () => {} };
      const nodes = await OneMind.fromEnv(env(p.ca), quick).nodes.list();
      expect(nodes.length).toBe(1);
      await expect(OneMind.fromEnv(env(p.other), quick).nodes.list()).rejects.toThrow(); // another CA: rejected
    } finally {
      server.close();
      p.cleanup();
    }
  });
});
