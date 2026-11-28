// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { Onboarding } from '../Onboarding';
import { SetupMap } from './SetupMap';

afterEach(() => vi.unstubAllGlobals());

it('renders the same map before and after the beat, even with reduced motion and Escape', async () => {
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  const { container } = render(<SetupMap boxName="hill-hub" timeZone="America/New_York" ready />);
  const svg = container.querySelector('svg')!;
  const original = svg.outerHTML;
  const started = vi.fn(() => ({ finish: vi.fn(), cancel: vi.fn(), finished: Promise.resolve() }));
  for (const element of svg.querySelectorAll('[data-map-draw], [data-map-ring]')) {
    Object.defineProperty(element, 'animate', { value: started });
  }
  await userEvent.click(screen.getByRole('button', { name: 'Draw my map' }));
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(svg.outerHTML).toBe(original);
  expect(screen.getByText('Asset map preview, planned')).toBeVisible();
  expect(started).toHaveBeenCalledTimes(5);
  for (const [frames, timing] of started.mock.calls as unknown as [Keyframe[], KeyframeAnimationOptions][]) {
    expect(timing).toEqual({ duration: 160, delay: 0 });
    expect(frames.every((frame) => Object.keys(frame).join() === 'opacity')).toBe(true);
  }
  await userEvent.click(screen.getByRole('button', { name: 'Replay' }));
  expect(svg.outerHTML).toBe(original);
  expect(started).toHaveBeenCalledTimes(10);
});

it('keeps input focus on edits and moves focus to the next step heading with reduced motion', async () => {
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  render(<Onboarding apps={[]} onFinish={vi.fn()} />);
  const user = userEvent.setup();
  const name = screen.getByLabelText('Box name');
  await user.type(name, 'hill-hub');
  expect(name).toHaveFocus();
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  expect(screen.getByRole('heading', { level: 2, name: 'Create the owner' })).toHaveFocus();
  expect(screen.getByRole('button', { name: 'Create passkey' })).toBeDisabled();
  expect(screen.queryByText('Passkey saved')).toBeNull();
});
