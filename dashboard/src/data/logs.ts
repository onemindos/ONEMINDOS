// SPDX-License-Identifier: Apache-2.0
// Turn the plain-text body of GET /v1/apps/{id}/logs (one line per row, secrets already redacted
// by the gateway) into the rows the @onemind/ui LogViewer shows. The hub sends no structure, so a
// level is read from the text only when the line says one, and a time only when the line starts
// with one. A line without its own time takes the moment it was read: the screen says so.
import type { ComponentProps } from 'react';
import type { LogViewer } from '@onemind/ui';

export type ViewerLine = ComponentProps<typeof LogViewer>['lines'][number];

const STAMP = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))\s+/;
const LEVELS: Array<[RegExp, ViewerLine['level']]> = [
  [/\b(?:fatal|panic|error|err|fail(?:ed|ure)?)\b/i, 'error'],
  [/\b(?:warn(?:ing)?)\b/i, 'warn'],
  [/\b(?:debug|trace)\b/i, 'debug'],
];

export function levelOf(text: string): ViewerLine['level'] {
  for (const [re, level] of LEVELS) if (re.test(text)) return level;
  return 'info';
}

export function parseLogs(body: string, readAt: Date): { lines: ViewerLine[]; untimed: number } {
  const lines: ViewerLine[] = [];
  let untimed = 0;
  for (const raw of body.split('\n')) {
    if (!raw.trim()) continue;
    const m = STAMP.exec(raw);
    const at = m && !Number.isNaN(Date.parse(m[1]!)) ? new Date(m[1]!).toISOString() : undefined;
    if (!at) untimed += 1;
    const text = at && m ? raw.slice(m[0].length) : raw;
    lines.push({ at: at ?? readAt.toISOString(), level: levelOf(text), text });
  }
  return { lines, untimed };
}
