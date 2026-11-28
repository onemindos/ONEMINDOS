// SPDX-License-Identifier: Apache-2.0
import type { CatalogApp } from '../api/types';

/** The Needs line, from the gateway's normalised machine_needs (#724), so either manifest spelling reads the same.
 * Only a gateway older than #724 lacks it; then the older requires keys are read. */
export function needs(app: Pick<CatalogApp, 'requires' | 'machine_needs'>): string {
  const req = app.machine_needs?.requires;
  const acc = req ? req.accelerator : app.requires.gpu ? { capability: 'gpu-compute' } : undefined;
  const memoryMb = req ? req.memoryMb : app.requires.minMemoryMb;
  const count = acc?.count && acc.count > 1 ? acc.count : 1;
  const gpu = acc?.capability === 'gpu-compute';
  const kind = `${gpu ? 'GPU' : 'accelerator'}${count > 1 ? 's' : ''}${acc?.capability && !gpu ? ` (${acc.capability})` : ''}`;
  const card = acc ? `${count > 1 ? count : gpu ? 'a' : 'an'} ${kind}${acc.minMemoryMb ? ` with ${acc.minMemoryMb} MB of its own memory` : ''}` : null;
  return [card, memoryMb ? `${memoryMb} MB of memory` : null].filter(Boolean).join(', ') || 'Nothing special';
}
