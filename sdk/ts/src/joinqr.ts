// SPDX-License-Identifier: Apache-2.0
// The join QR (docs/architecture/FABRIC.md §4.3): `onemind-join:v2?hub=…[&alt=…][&mdns=…]&ca=…&code=…&kind=…`
// and the older `onemind-join:v1?code=…&ca=…[&role=…]&hub=…`. Parses exactly as
// core/onemind_core/fabric.py parse_join_qr and internal/fabric/join.go ParseQR do; all three run
// sdk/testdata/join-qr/vectors.json. URL and URLSearchParams are not used on purpose: they accept
// '+', IP shorthands and IPv6 literals the other languages read differently.

export const JOIN_QR_MAX_LENGTH = 640;
export const JOIN_KINDS = ["worker", "leaf", "phone", "desktop", "browser", "sensor"] as const;
export type JoinKind = (typeof JOIN_KINDS)[number];

/** A parsed join QR. v1 has no alt or mdns, and its optional `role` lands in `kind` ("" when absent). */
export interface JoinQR {
  version: 1 | 2;
  code: string;
  ca: string;
  hub: string;
  kind: JoinKind | "";
  alt: string;
  mdns: string;
}

export type JoinQRReason =
  | "charset" | "length" | "prefix" | "version" | "syntax" | "unknown_field" | "duplicate" | "missing_field"
  | "code" | "ca" | "kind" | "role" | "hub" | "alt" | "mdns";

/** A refused join QR; `reason` is the same word in Python, Go and TypeScript. */
export class JoinQRError extends Error {
  readonly reason: JoinQRReason;
  constructor(reason: JoinQRReason, message: string) {
    super(message);
    this.reason = reason;
    this.name = "JoinQRError";
  }
}

const NON_ASCII = /[^\x00-\x7f]/;
const PREFIX = /^onemind-join:v([0-9]+)\?/;
const KEY = /^[a-z]+$/;
const VALUE = /^[A-Za-z0-9._~%:/-]+$/;
const HEX2 = /^[0-9A-Fa-f]{2}$/;
const CODE_V1 = /^[0-9A-Za-z]{4}-?[0-9A-Za-z]{4}-?[0-9A-Za-z]{4}$/;
const CODE_V2 = /^[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}$/;
const CA = /^[0-9a-f]{64}$/;
const HOST_PORT = /^([A-Za-z0-9.-]{1,253})(?::([1-9][0-9]{0,4}))?$/;
const LABEL = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
const DIGITS = /^[0-9]+$/;
const OCTET = /^(?:0|[1-9][0-9]{0,2})$/;
const MDNS = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.local$/;
const FIELDS: Record<1 | 2, readonly string[]> = { 1: ["code", "ca", "role", "hub"], 2: ["hub", "alt", "mdns", "ca", "code", "kind"] };
const REQUIRED: Record<1 | 2, readonly string[]> = { 1: ["code", "ca", "hub"], 2: ["hub", "ca", "code", "kind"] };

function unescape(v: string): string | undefined {
  let out = "";
  for (let i = 0; i < v.length; i++) {
    let c = v.charCodeAt(i);
    if (c === 0x25) {
      const pair = v.slice(i + 1, i + 3);
      if (!HEX2.test(pair)) return undefined;
      c = parseInt(pair, 16);
      i += 2;
    }
    if (c < 0x21 || c > 0x7e) return undefined;
    out += String.fromCharCode(c);
  }
  return out;
}

function https(v: string): string | undefined {
  if (!v.startsWith("https://")) return undefined;
  let rest = v.slice("https://".length);
  if (rest.endsWith("/")) rest = rest.slice(0, -1);
  const m = HOST_PORT.exec(rest);
  if (!m || (m[2] !== undefined && Number(m[2]) > 65535)) return undefined;
  const host = m[1]!.toLowerCase();
  const labels = host.split(".");
  if (!labels.every((l) => LABEL.test(l))) return undefined;
  if (DIGITS.test(labels[labels.length - 1]!) && !(labels.length === 4 && labels.every((l) => OCTET.test(l) && Number(l) <= 255))) {
    return undefined;
  }
  return "https://" + host + (m[2] !== undefined ? ":" + m[2] : "");
}

const fail = (reason: JoinQRReason, message: string): never => {
  throw new JoinQRError(reason, message);
};

/** Parse a scanned or pasted join QR; throws JoinQRError. Nothing is fetched. */
export function parseJoinQR(payload: string): JoinQR {
  if (typeof payload !== "string") fail("length", `a join QR is at most ${JOIN_QR_MAX_LENGTH} characters`);
  // ASCII first: TS counts UTF-16 units, Python code points and Go bytes, so a length check on a
  // non-ASCII payload would give a different reason word in each language.
  if (NON_ASCII.test(payload)) fail("charset", "a join QR is plain ASCII text");
  if (payload.length > JOIN_QR_MAX_LENGTH) fail("length", `a join QR is at most ${JOIN_QR_MAX_LENGTH} characters`);
  const m = PREFIX.exec(payload) ?? fail("prefix", "not a OneMind join code (expected onemind-join:v2?…)");
  if (m[1] !== "1" && m[1] !== "2") fail("version", `unsupported join QR version v${m[1]} (this build reads v1 and v2)`);
  const version = Number(m[1]) as 1 | 2;
  const fields = new Map<string, string>();
  for (const part of payload.slice(m[0].length).split("&")) {
    const eq = part.indexOf("=");
    const key = eq < 0 ? part : part.slice(0, eq);
    const raw = eq < 0 ? "" : part.slice(eq + 1);
    const value = eq >= 0 && KEY.test(key) && VALUE.test(raw) ? unescape(raw) : undefined;
    if (value === undefined) fail("syntax", "join QR is malformed (expected key=value pairs joined by &)");
    if (!FIELDS[version].includes(key)) fail("unknown_field", `join QR v${version} has no field "${key}"`);
    if (fields.has(key)) fail("duplicate", `join QR repeats the field "${key}"`);
    fields.set(key, value!);
  }
  for (const key of REQUIRED[version]) if (!fields.has(key)) fail("missing_field", `join QR v${version} needs the field "${key}"`);
  const code = fields.get("code")!;
  let ca = fields.get("ca")!;
  let kind: string;
  if (version === 1) {
    kind = fields.get("role") ?? "";
    ca = ca.toLowerCase();
    if (!CODE_V1.test(code)) fail("code", "join code must look like 7KQ4-M2XP-9D3F");
  } else {
    kind = fields.get("kind")!;
    if (!CODE_V2.test(code)) fail("code", "join code must look like 7KQ4-M2XP-9D3F (Crockford, upper case, two dashes)");
  }
  if (!CA.test(ca)) fail("ca", "the box CA fingerprint must be 64 lower-case hex characters");
  if (version === 1 && kind !== "" && kind !== "worker" && kind !== "leaf") fail("role", "role must be worker or leaf");
  if (version === 2 && !(JOIN_KINDS as readonly string[]).includes(kind)) fail("kind", `kind must be one of ${JOIN_KINDS.join(", ")}`);
  const hub = https(fields.get("hub")!) ?? fail("hub", "hub must be an https URL such as https://box.local (no user, path or query)");
  const rawAlt = fields.get("alt");
  const alt = rawAlt === undefined ? "" : https(rawAlt) ?? fail("alt", "alt must be an https URL such as https://box.example.net (no user, path or query)");
  const mdns = fields.get("mdns") ?? "";
  if (fields.has("mdns") && !MDNS.test(mdns)) fail("mdns", "mdns must be one lower-case name ending in .local, such as box1.local");
  return { version, code, ca, hub, kind: kind as JoinKind | "", alt, mdns };
}
