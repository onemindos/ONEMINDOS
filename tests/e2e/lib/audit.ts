// SPDX-License-Identifier: Apache-2.0
/**
 * Independent re-check of the gateway's hash-chained audit log (contract §3 "Audit";
 * core/onemind_core/audit.py):
 *
 *   hash = sha256(prev_hash + canonical_json(line without prev_hash and hash))
 *
 * canonical_json is Python's json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False).
 * The first line links to 64 zeros. Written separately from the Python code on purpose: two
 * implementations that agree are better evidence than one checking itself.
 */
import { createHash } from 'node:crypto';

export const GENESIS = '0'.repeat(64);

export interface AuditRecord {
  seq: number;
  ts: string;
  event: string;
  principal: { id: string; kind: string; role?: string } | null;
  action_id: string | null;
  data: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

/** Python-compatible canonical JSON. Floats are refused: the audit log has none, and their text form differs. */
export function canonicalJson(v: unknown): string {
  if (v === null || typeof v === 'boolean' || typeof v === 'string') return JSON.stringify(v);
  if (typeof v === 'number') {
    if (!Number.isInteger(v)) throw new Error(`canonicalJson: non-integer number ${v}`);
    return String(v);
  }
  if (Array.isArray(v)) return `[${v.map(canonicalJson).join(',')}]`;
  if (typeof v === 'object') {
    // Python sorts str keys by code point; compare code points, not UTF-16 units.
    const keys = Object.keys(v as object).sort((a, b) => {
      const x = [...a].map((c) => c.codePointAt(0)!);
      const y = [...b].map((c) => c.codePointAt(0)!);
      for (let i = 0; i < Math.min(x.length, y.length); i++) if (x[i] !== y[i]) return x[i] - y[i];
      return x.length - y.length;
    });
    return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJson((v as Record<string, unknown>)[k])}`).join(',')}}`;
  }
  throw new Error(`canonicalJson: unsupported ${typeof v}`);
}

export function chainHash(prevHash: string, body: Record<string, unknown>): string {
  return createHash('sha256').update(prevHash + canonicalJson(body), 'utf8').digest('hex');
}

export interface ChainResult {
  ok: boolean;
  records: AuditRecord[];
  /** 1-based line of the first problem, or undefined. */
  firstBadLine?: number;
  problem?: string;
}

export function verifyChain(text: string): ChainResult {
  const records: AuditRecord[] = [];
  let prev = GENESIS;
  const lines = text.split('\n').filter((l) => l.trim() !== '');
  for (let i = 0; i < lines.length; i++) {
    let rec: AuditRecord;
    try {
      rec = JSON.parse(lines[i]) as AuditRecord;
    } catch {
      return { ok: false, records, firstBadLine: i + 1, problem: 'not JSON' };
    }
    const { prev_hash, hash, ...body } = rec;
    if (prev_hash !== prev) return { ok: false, records, firstBadLine: i + 1, problem: 'prev_hash does not link' };
    if (chainHash(prev_hash, body) !== hash) return { ok: false, records, firstBadLine: i + 1, problem: 'hash mismatch' };
    if (i > 0 && rec.seq !== records[i - 1].seq + 1) return { ok: false, records, firstBadLine: i + 1, problem: 'seq gap' };
    records.push(rec);
    prev = hash;
  }
  return { ok: lines.length > 0, records, problem: lines.length ? undefined : 'empty log' };
}
