// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { Onboarding } from './Onboarding';
import { emptyDraft } from './firstRun';

afterEach(() => { delete (HTMLElement.prototype as { animate?: unknown }).animate; });

it('keeps the leaving card hidden until the next step has rendered, so it never flashes back', async () => {
  const user = userEvent.setup();
  const exitCancelledWhen: boolean[] = [];
  Object.defineProperty(HTMLElement.prototype, 'animate', {
    configurable: true,
    value: vi.fn((frames: Keyframe[], timing: KeyframeAnimationOptions) => {
      const leaving = timing.fill === 'forwards';
      void frames;
      return {
        finished: Promise.resolve(),
        finish: vi.fn(),
        cancel: vi.fn(() => { if (leaving) exitCancelledWhen.push(!!screen.queryByRole('heading', { level: 2, name: 'Where is your place?' })); }),
      };
    }),
  });
  render(<Onboarding apps={[]} initial={{ ...emptyDraft('UTC'), boxName: 'home-hub' }} onFinish={() => {}} />);
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  await waitFor(() => expect(screen.getByRole('heading', { level: 2, name: 'Where is your place?' })).toBeInTheDocument());
  await waitFor(() => expect(exitCancelledWhen).toEqual([true]));
});
