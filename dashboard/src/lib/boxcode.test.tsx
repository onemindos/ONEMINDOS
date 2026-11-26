// SPDX-License-Identifier: Apache-2.0
// N-1 b: the dialog that asks for the code the box's own screen shows. The API client calls askBoxCode
// (no React there); the host mounted in the app answers it.
import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { askBoxCode, BoxCodeHost } from './boxcode';

describe('askBoxCode', () => {
  it('without the host it refuses plainly instead of hanging', async () => {
    await expect(askBoxCode('users.update')).rejects.toMatchObject({ reason: 'box_code_required' });
  });

  it('the host asks, takes six digits (spaces allowed) and answers the promise', async () => {
    render(<BoxCodeHost />);
    let p!: Promise<string>;
    act(() => { p = askBoxCode('users.update'); });
    expect(await screen.findByText('Confirm at the box')).toBeTruthy();
    expect(screen.getByText(/users update/)).toBeTruthy();
    const go = screen.getByRole('button', { name: 'Continue' }) as HTMLButtonElement;
    fireEvent.change(screen.getByLabelText("Code on the box's screen"), { target: { value: '482' } });
    expect(go.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Code on the box's screen"), { target: { value: '482 913' } });
    fireEvent.click(go);
    await expect(p).resolves.toBe('482913');
  });

  it('cancelling changes nothing', async () => {
    render(<BoxCodeHost />);
    let p!: Promise<string>;
    act(() => { p = askBoxCode('approve act-1'); });
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
    await expect(p).rejects.toMatchObject({ reason: 'cancelled' });
  });
});
