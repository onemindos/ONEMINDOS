// SPDX-License-Identifier: Apache-2.0
/**
 * The actions this run created, so the audit spec checks exactly these (a reused hub also holds
 * earlier runs and verify.sh's own, partly denied, requests). The harness removes the file first.
 */
import { appendFileSync, existsSync, mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

export interface RunAction {
  id: string;
  type: 'app.install' | 'app.remove';
  by: 'owner' | 'agent';
}

const file = () => join(process.env.E2E_OUT ?? 'out', 'golden-actions.jsonl');

export function recordAction(a: RunAction): void {
  mkdirSync(process.env.E2E_OUT ?? 'out', { recursive: true });
  appendFileSync(file(), JSON.stringify(a) + '\n');
}

export function recordedActions(): RunAction[] {
  if (!existsSync(file())) return [];
  return readFileSync(file(), 'utf8')
    .split('\n')
    .filter(Boolean)
    .map((l) => JSON.parse(l) as RunAction);
}
