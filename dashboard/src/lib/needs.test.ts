// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import type { MachineNeedsBlock } from '../api/types';
import { needs } from './needs';

const normalised = (requires: MachineNeedsBlock, raw: Record<string, unknown> = {}) =>
  ({ requires: raw, machine_needs: { requires, recommends: {}, supports: {} } });

describe('the Needs line (#724)', () => {
  it('reads machine_needs, so an app in the new spelling that needs a GPU and 32 GB says so', () => {
    const app = normalised({ memoryMb: 32768, accelerator: { capability: 'gpu-compute' } }, { memoryMb: 32768, accelerator: { capability: 'gpu-compute' } });
    expect(needs(app)).toBe('a GPU, 32768 MB of memory');
  });

  it('reads the same for both spellings, because it never reads the raw requires when machine_needs is there', () => {
    const older = normalised({ memoryMb: 32768, accelerator: { capability: 'gpu-compute', minMemoryMb: 8192 } }, { gpu: true, minMemoryMb: 32768, minVramMb: 8192 });
    const newer = normalised({ memoryMb: 32768, accelerator: { capability: 'gpu-compute', minMemoryMb: 8192 } }, { memoryMb: 32768, accelerator: { capability: 'gpu-compute', minMemoryMb: 8192 } });
    expect(needs(older)).toBe('a GPU with 8192 MB of its own memory, 32768 MB of memory');
    expect(needs(newer)).toBe(needs(older));
  });

  it('names other accelerators and counts', () => {
    expect(needs(normalised({ accelerator: { capability: 'gpu-compute', count: 2 } }))).toBe('2 GPUs');
    expect(needs(normalised({ accelerator: { capability: 'npu' } }))).toBe('an accelerator (npu)');
    expect(needs(normalised({ accelerator: { capability: 'npu', count: 3 } }))).toBe('3 accelerators (npu)');
    expect(needs(normalised({ accelerator: {} }))).toBe('an accelerator');
  });

  it('says nothing special when no fact is stated', () => {
    expect(needs(normalised({ arch: ['amd64'] }))).toBe('Nothing special');
  });

  it('falls back to the older keys only for a gateway that sends no machine_needs', () => {
    expect(needs({ requires: { gpu: true, minMemoryMb: 4096 } })).toBe('a GPU, 4096 MB of memory');
    expect(needs({ requires: { gpu: false } })).toBe('Nothing special');
  });
});
