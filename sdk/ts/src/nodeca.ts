// SPDX-License-Identifier: Apache-2.0
// A fetch that trusts one CA (the box CA, ONEMIND_GATEWAY_CA) and nothing else, for Node. Node's
// global fetch has no per-request CA option (it would need the `undici` package as a dependency),
// so this uses node:https, imported lazily: browsers and React Native never load it.

/* eslint-disable @typescript-eslint/no-explicit-any */
export function caFetch(ca: string): typeof fetch {
  return async (input: any, init: any = {}) => {
    const spec = "node:" + "https"; // not a literal: bundlers must not try to resolve it for browsers
    const [https, stream]: any[] = await Promise.all([import(/* @vite-ignore */ spec), import(/* @vite-ignore */ "node:" + "stream")]);
    const url = new URL(typeof input === "string" ? input : input.url ?? String(input));
    const headers: Record<string, string> = {};
    new Headers(init.headers).forEach((v, k) => (headers[k] = v));
    return new Promise<Response>((resolve, reject) => {
      const signal: AbortSignal | undefined = init.signal ?? undefined;
      const req = https.request(
        url,
        { method: init.method ?? "GET", headers, ca, minVersion: "TLSv1.2", signal }, // `ca` replaces the system roots
        (res: any) => {
          const h = new Headers();
          for (const [k, v] of Object.entries(res.headers as Record<string, string | string[] | undefined>)) {
            for (const one of Array.isArray(v) ? v : v === undefined ? [] : [v]) h.append(k, one);
          }
          const nobody = res.statusCode === 204 || res.statusCode === 304;
          resolve(new Response(nobody ? null : (stream.Readable.toWeb(res) as ReadableStream), { status: res.statusCode, headers: h }));
        },
      );
      req.on("error", reject);
      if (init.body !== undefined && init.body !== null) req.write(init.body);
      req.end();
    });
  };
}
