// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { Onboarding } from '../Onboarding';
import { SetupMap } from './SetupMap';

afterEach(() => vi.unstubAllGlobals());

const reduce = () => vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }));

function spyOn(svg: SVGSVGElement, selector: string) {
  const started = vi.fn(() => ({ finish: vi.fn(), cancel: vi.fn(), finished: Promise.resolve() }));
  for (const element of svg.querySelectorAll(selector)) Object.defineProperty(element, 'animate', { value: started });
  return started;
}

it('renders the same map before and after the beat, even with reduced motion and Escape', async () => {
  reduce();
  const { container } = render(<SetupMap boxName="hill-hub" timeZone="America/New_York" ready />);
  const svg = container.querySelector('svg')!;
  const original = svg.outerHTML;
  const started = spyOn(svg, '[data-map-grid], [data-map-draw], [data-map-pin], [data-map-ring]');
  await userEvent.click(screen.getByRole('button', { name: 'Draw my map' }));
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(svg.outerHTML).toBe(original);
  expect(screen.getByText('Asset map preview, planned')).toBeVisible();
  // Grid, four contours, the box and its ring: 7, under the limit of 9 running at once.
  expect(started).toHaveBeenCalledTimes(7);
  for (const [frames, timing] of started.mock.calls as unknown as [Keyframe[], KeyframeAnimationOptions][]) {
    expect(timing).toEqual({ duration: 160, delay: 0 });
    expect(frames.every((frame) => Object.keys(frame).join() === 'opacity')).toBe(true);
  }
  await userEvent.click(screen.getByRole('button', { name: 'Replay' }));
  expect(svg.outerHTML).toBe(original);
  expect(started).toHaveBeenCalledTimes(14);
});

it('starts empty, and each answer adds one honest thing', () => {
  const { container, rerender } = render(<SetupMap boxName="" timeZone="UTC" drawn={false} />);
  expect(container.querySelector('[data-map-grid]')).toBeNull();
  expect(screen.getByText('Your map starts empty')).toBeInTheDocument();
  expect(screen.queryByRole('button')).toBeNull();
  rerender(<SetupMap boxName="hill-hub" placeName="Rivera Home" address="12 Orchard Lane" timeZone="UTC" drawn
    location={{ lat: 40.7128, lon: -74.006, source: 'typed' }} approvals waiting={2} backup />);
  expect(screen.getByText('Rivera Home')).toBeInTheDocument();
  expect(screen.getByText('12 Orchard Lane')).toBeInTheDocument();
  expect(screen.getByText(/40\.71280° N, 74\.00600° W · from coordinates you typed/)).toBeInTheDocument();
  expect(container.querySelector('.oms-setup-map-gate')).not.toBeNull();
  expect(container.querySelectorAll('.oms-setup-map-tile')).toHaveLength(2);
  expect(container.querySelector('.oms-setup-map-backup')).not.toBeNull();
  const facts = screen.getByRole('list', { name: 'On your map' });
  expect(facts).toHaveTextContent('2 install requests waiting for you');
  expect(facts).toHaveTextContent('AI can ask, only you approve');
});

it('moves the map to a new position with transform and opacity only, and only opacity with reduced motion', () => {
  const where = (lat: number, lon: number) => ({ lat, lon, source: 'link' as const });
  const { container, rerender } = render(<SetupMap boxName="hill-hub" timeZone="UTC" drawn />);
  const svg = container.querySelector('svg')!;
  const started = spyOn(svg, '[data-map-pan], [data-map-pin]');
  rerender(<SetupMap boxName="hill-hub" timeZone="UTC" drawn location={where(51.5, -0.12)} />);
  expect(started).toHaveBeenCalledTimes(2);
  const props = (started.mock.calls as unknown as [Keyframe[]][]).flatMap(([frames]) => frames.flatMap((f) => Object.keys(f)));
  expect(new Set(props)).toEqual(new Set(['transform', 'opacity']));
  reduce();
  rerender(<SetupMap boxName="hill-hub" timeZone="UTC" drawn location={where(48.85, 2.35)} />);
  const reduced = (started.mock.calls as unknown as [Keyframe[]][]).slice(2);
  expect(reduced).toHaveLength(2);
  expect(reduced.every(([frames]) => frames.every((f) => Object.keys(f).join() === 'opacity'))).toBe(true);
  expect(screen.getByText(/from a map link you pasted/)).toBeInTheDocument();
});

it('keeps input focus on edits and moves focus to the next step heading with reduced motion', async () => {
  reduce();
  render(<Onboarding apps={[]} onFinish={vi.fn()} deviceLocation={undefined} />);
  const user = userEvent.setup();
  const name = screen.getByLabelText('Box name');
  await user.type(name, 'hill-hub');
  expect(name).toHaveFocus();
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  expect(screen.getByRole('heading', { level: 2, name: 'Where is your place?' })).toHaveFocus();
  await user.click(screen.getByRole('button', { name: 'Skip' }));
  expect(screen.getByRole('heading', { level: 2, name: 'AI can ask. Only you approve.' })).toHaveFocus();
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  expect(screen.getByRole('heading', { level: 2, name: 'Create the owner' })).toHaveFocus();
  expect(screen.getByRole('button', { name: 'Create passkey' })).toBeDisabled();
  expect(screen.queryByText('Passkey saved')).toBeNull();
});
