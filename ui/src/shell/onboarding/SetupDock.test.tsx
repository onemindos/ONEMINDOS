// SPDX-License-Identifier: Apache-2.0
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { Onboarding } from '../Onboarding';
import { ONBOARDING_STEPS, emptyDraft, type StarterApp } from '../firstRun';
import { SetupDock } from './SetupDock';

const at = (id: string) => ONBOARDING_STEPS.findIndex((s) => s.id === id);
const app = (id: string, name: string): StarterApp => ({ id, name, tagline: name, category: 'files', deployClass: 'market-verified', minMemoryMb: 256 });
const animateCalls: Array<{ el: Element; frames: Keyframe[]; timing: KeyframeAnimationOptions; cancel: ReturnType<typeof vi.fn> }> = [];

function fakeAnimate() {
  Object.defineProperty(Element.prototype, 'animate', {
    configurable: true,
    value: vi.fn(function (this: Element, frames: Keyframe[], timing: KeyframeAnimationOptions) {
      const cancel = vi.fn();
      animateCalls.push({ el: this, frames, timing, cancel });
      return { finished: Promise.resolve(), finish: vi.fn(), cancel };
    }),
  });
}
afterEach(() => { animateCalls.length = 0; delete (Element.prototype as { animate?: unknown }).animate; vi.unstubAllGlobals(); });

it('drops each newly ticked app into the dock, staggered, waiting for approval, and takes unticked ones out', () => {
  fakeAnimate();
  const { rerender, container } = render(<SetupDock apps={[]} />);
  expect(screen.getByText(/Apps you tick join it, waiting for your approval/)).toBeInTheDocument();
  rerender(<SetupDock apps={[{ id: 'immich', name: 'Immich', category: 'files' }, { id: 'vault', name: 'Vaultwarden', category: 'security' }]} />);
  expect(container.querySelectorAll('[data-dock-app]')).toHaveLength(2);
  expect(screen.getByText(/then Immich, Vaultwarden, each waiting for your approval/)).toBeInTheDocument();
  expect(animateCalls.map((c) => (c.el as HTMLElement).dataset.dockApp)).toEqual(['immich', 'vault']);
  expect(animateCalls.map((c) => c.timing.delay)).toEqual([0, 50]);
  expect(new Set(animateCalls.flatMap((c) => c.frames.flatMap((f) => Object.keys(f))))).toEqual(new Set(['opacity', 'transform']));
  // A re-render with the same apps animates nothing again.
  rerender(<SetupDock apps={[{ id: 'immich', name: 'Immich', category: 'files' }, { id: 'vault', name: 'Vaultwarden', category: 'security' }]} />);
  expect(animateCalls).toHaveLength(2);
  rerender(<SetupDock apps={[{ id: 'vault', name: 'Vaultwarden', category: 'security' }]} />);
  expect(container.querySelector('[data-dock-app="immich"]')).toBeNull();
  expect(animateCalls).toHaveLength(2);
});

it('never animates more than six tiles at once, and only opacity with reduced motion', () => {
  fakeAnimate();
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  const { rerender } = render(<SetupDock apps={[]} />);
  rerender(<SetupDock apps={Array.from({ length: 8 }, (_, i) => ({ id: `a${i}`, name: `App ${i}`, category: 'files' }))} />);
  expect(animateCalls).toHaveLength(6);
  expect(animateCalls.every((c) => c.frames.every((f) => Object.keys(f).join() === 'opacity') && c.timing.duration === 160)).toBe(true);
});

it('the desktop assembles on the apps step as the owner ticks apps', async () => {
  const user = userEvent.setup();
  const apps = [app('immich', 'Immich'), app('notes', 'Notes')];
  const { container } = render(<Onboarding apps={apps} initialStep={at('apps')} initial={{ ...emptyDraft('UTC'), boxName: 'home-hub' }} onSaveSettings={vi.fn()} onFinish={vi.fn()} />);
  expect(container.querySelectorAll('[data-dock-app]')).toHaveLength(0);
  await user.click(screen.getByRole('checkbox', { name: /Immich/ }));
  expect(container.querySelector('.oms-setup-dock [data-dock-app="immich"]')).not.toBeNull();
  expect(container.querySelectorAll('.oms-setup-map-tile')).toHaveLength(1);
  await user.click(screen.getByRole('checkbox', { name: /Immich/ }));
  expect(container.querySelectorAll('[data-dock-app]')).toHaveLength(0);
});

it('hands off to the desktop only after the exit, and brings the wizard back when finishing fails', async () => {
  const user = userEvent.setup();
  fakeAnimate();
  const finish = vi.fn().mockRejectedValueOnce(new Error('Hub unavailable')).mockResolvedValueOnce(undefined);
  const { container } = render(<Onboarding apps={[]} initialStep={at('done')} initial={{ ...emptyDraft('UTC'), boxName: 'home-hub' }} onSaveSettings={vi.fn()} finishLabel="Open my map" onFinish={finish} />);
  animateCalls.length = 0;
  await user.click(screen.getByRole('button', { name: /Open my map/ }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Hub unavailable');
  const exit = animateCalls.filter((c) => c.el === container.querySelector('.oms-onb') || c.el.classList.contains('oms-setup-map'));
  expect(exit).toHaveLength(2);
  expect(exit.every((c) => c.timing.fill === 'forwards')).toBe(true);
  // Finishing failed: the faded-out wizard and the grown map are put back.
  expect(exit.every((c) => c.cancel.mock.calls.length > 0)).toBe(true);
  expect(finish).toHaveBeenCalledTimes(1);
  await act(async () => { await user.click(screen.getByRole('button', { name: /Open my map/ })); });
  await waitFor(() => expect(finish).toHaveBeenCalledTimes(2));
});
