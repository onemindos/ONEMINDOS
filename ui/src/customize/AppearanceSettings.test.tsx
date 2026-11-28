// SPDX-License-Identifier: Apache-2.0
// Appearance screen: states (loading, error, stale, ready), keyboard and screen-reader basics
// (axe-core), and that choices reach the document and the store.
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { afterEach, describe, expect, it } from 'vitest';
import { ACCENTS } from './accents';
import { AppearanceSettings } from './AppearanceSettings';
import { CustomizeProvider } from './CustomizeProvider';
import { DEFAULT_PREFERENCES, STYLE_ID, clearPreferences, type AppearancePreferences } from './preferences';
import { PendingStore, PreferencesError, type PreferencesStore, type StoredPreferences } from './store';
import { WallpaperLayer } from './WallpaperLayer';

async function noAxeViolations(container: Element) {
  const res = await axe.run(container, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
  expect(res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(' | ')}`)).toEqual([]);
}

class MemoryStore implements PreferencesStore {
  saved: AppearancePreferences[] = [];
  image: string | null = null;
  constructor(
    readonly kind: 'local' | 'hub',
    private doc: StoredPreferences | Error,
    private saveFails = false,
  ) {}
  async load() {
    if (this.doc instanceof Error) throw this.doc;
    return this.doc;
  }
  async save(prefs: AppearancePreferences) {
    if (this.saveFails) throw new PreferencesError('network', 'The hub could not be reached.');
    this.saved.push(prefs);
    return { prefs, updatedAt: '2026-11-12T15:00:00.000Z' };
  }
  async loadWallpaperImage() {
    return this.image;
  }
  async saveWallpaperImage(d: string | null) {
    this.image = d;
  }
}

const NOW = () => new Date('2026-11-12T15:00:00Z');
const saved = (p: Partial<AppearancePreferences> = {}): StoredPreferences => ({ prefs: { ...DEFAULT_PREFERENCES, ...p }, updatedAt: '2026-11-12T14:00:00Z' });

function mount(store: PreferencesStore, cache?: PreferencesStore) {
  return render(
    <CustomizeProvider store={store} cache={cache} now={NOW} saveDelay={0}>
      <WallpaperLayer portal={false} />
      <AppearanceSettings />
    </CustomizeProvider>,
  );
}

afterEach(() => clearPreferences());

describe('AppearanceSettings', () => {
  it('starts in Contour with the run bar off and applies a pack without resetting text size', async () => {
    const store = new MemoryStore('local', saved({ fontScale: 1.25 }));
    mount(store);
    const bar = await screen.findByRole('switch', { name: 'Show the run bar (Alt R)' });
    expect(bar).not.toBeChecked();
    expect(DEFAULT_PREFERENCES.wallpaper).toBe('contour');
    await userEvent.click(bar);
    await userEvent.click(screen.getByRole('button', { name: 'Harbor pack' }));
    await waitFor(() => expect(store.saved.at(-1)).toMatchObject({
      wallpaper: 'signal', accentPreset: 'copper', theme: 'dark', commandBar: true, fontScale: 1.25,
    }));
  });

  it('offers every Atlas and Console pack', async () => {
    mount(new MemoryStore('local', saved({})));
    for (const n of ['Atlas Night', 'Atlas Day', 'Night Watch', 'Greenhouse', 'Harbor', 'OneMind', 'OneMind Light', 'Field', 'Village', 'Mono']) {
      expect(await screen.findByRole('button', { name: `${n} pack` })).toBeInTheDocument();
    }
    expect(screen.queryByRole('button', { name: 'Paper pack' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Console Default pack' })).toBeNull();
  });

  it('shows a labelled loading state', () => {
    mount(new PendingStore());
    expect(screen.getByRole('status')).toHaveTextContent('Loading your appearance');
  });

  it('shows an error with a retry when nothing can be loaded', async () => {
    mount(new MemoryStore('hub', new PreferencesError('network', 'The hub could not be reached.')));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('could not be loaded');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('is honest when the hub is unreachable and a local copy is shown', async () => {
    const hub = new MemoryStore('hub', new PreferencesError('pending_contract', 'The hub does not store appearance yet (contract §12 pending).'));
    const local = new MemoryStore('local', saved({ accentSource: 'preset', accentPreset: 'rose' }));
    mount(hub, local);
    expect(await screen.findByText('Not synced')).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent('copy saved on this browser 1 h ago');
    expect(screen.getByRole('radio', { name: 'Rose' })).toBeChecked();
  });

  it('applies and saves a chosen accent, theme and density', async () => {
    const user = userEvent.setup();
    const store = new MemoryStore('local', saved());
    const { container } = mount(store);
    await screen.findByRole('heading', { name: 'Highlight colour' });
    await noAxeViolations(container);

    await user.click(screen.getByRole('radio', { name: 'Copper' }));
    await waitFor(() => expect(document.getElementById(STYLE_ID)?.textContent).toContain(ACCENTS.copper.light));
    await user.click(screen.getByRole('radio', { name: /^Dark/ }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    await user.click(screen.getByRole('radio', { name: 'Compact' }));
    expect(document.documentElement.getAttribute('data-om-density')).toBe('compact');
    await waitFor(() => expect(store.saved.at(-1)).toMatchObject({ accentSource: 'preset', accentPreset: 'copper', theme: 'dark', density: 'compact' }));
    expect(await screen.findByText('Saved on this browser')).toBeInTheDocument();
  });

  it('moves between radios with the arrow keys', async () => {
    const user = userEvent.setup();
    mount(new MemoryStore('local', saved({ density: 'comfortable' })));
    const comfy = await screen.findByRole('radio', { name: 'Comfortable' });
    comfy.focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('radio', { name: 'Compact' })).toBeChecked();
  });

  it('fixes a custom accent and explains the change', async () => {
    const user = userEvent.setup();
    mount(new MemoryStore('local', saved({ accentSource: 'custom', accentCustom: '#ffd400' })));
    const hex = await screen.findByRole('textbox', { name: 'Hex' });
    expect(screen.getByText(/Adjusted for readable text/)).toBeInTheDocument();
    await user.clear(hex);
    await user.type(hex, 'zz');
    expect(hex).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Enter a colour like #2a7f62.')).toBeInTheDocument();
  });

  it('shows the schedule fields and the current state', async () => {
    mount(new MemoryStore('local', saved({ theme: 'schedule' })));
    expect(await screen.findByLabelText(/Dark from/)).toHaveValue('19:00');
    expect(document.querySelector('.om-cz-schedule-now')).toHaveTextContent(/^Now: (light|dark) until \d\d:\d\d\.$/);
  });

  it('renders the wallpaper layer and disables sliders with no wallpaper', async () => {
    const user = userEvent.setup();
    const { container } = mount(new MemoryStore('local', saved({ wallpaper: 'tide' })));
    await screen.findByRole('radio', { name: 'Tide' });
    expect(container.querySelector('.om-cz-wallpaper')).toHaveAttribute('data-wallpaper', 'tide');
    await user.click(screen.getByRole('radio', { name: 'None' }));
    expect(container.querySelector('.om-cz-wallpaper')).toBeNull();
    expect(screen.getByRole('slider', { name: 'Dim' })).toBeDisabled();
    expect(screen.getByText('Pick a wallpaper to adjust it.')).toBeInTheDocument();
  });

  it('rejects an unsupported upload with a reason', async () => {
    const user = userEvent.setup({ applyAccept: false });
    const { container } = mount(new MemoryStore('local', saved()));
    await screen.findByRole('radio', { name: 'Aurora' });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(['x'], 'a.gif', { type: 'image/gif' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Use a JPEG, PNG or WebP image.');
  });

  it('resets with an undo', async () => {
    const user = userEvent.setup();
    mount(new MemoryStore('local', saved({ accentSource: 'preset', accentPreset: 'moss' })));
    await user.click(await screen.findByRole('button', { name: 'Reset to defaults' }));
    expect(screen.getByRole('radio', { name: 'Teal' })).toBeChecked();
    await user.click(screen.getByRole('button', { name: 'Undo' }));
    expect(screen.getByRole('radio', { name: 'Moss' })).toBeChecked();
  });

  it('keeps the change on this browser when the hub save fails', async () => {
    const user = userEvent.setup();
    const hub = new MemoryStore('hub', saved(), true);
    const local = new MemoryStore('local', saved());
    mount(hub, local);
    await user.click(await screen.findByRole('radio', { name: 'Ink' }));
    expect(await screen.findByText('Not saved to your account')).toBeInTheDocument();
    expect(screen.getByText(/Kept on this browser for now/)).toBeInTheDocument();
    await act(async () => undefined);
    expect(local.saved.at(-1)?.accentPreset).toBe('ink');
  });

  it('groups the ten packs under Atlas and Console with a preview each', async () => {
    const { container } = mount(new MemoryStore('local', saved({})));
    const atlas = await screen.findByRole('group', { name: 'From Atlas' });
    const consolePacks = screen.getByRole('group', { name: 'From Console' });
    expect(atlas.querySelectorAll('.om-cz-pack')).toHaveLength(5);
    expect(consolePacks.querySelectorAll('.om-cz-pack')).toHaveLength(5);
    expect(container.querySelectorAll('.om-cz-pack-mini')).toHaveLength(10);
  });

  it('writes the highlight colour as the accent tokens and keeps buttons red until switched off', async () => {
    const user = userEvent.setup();
    const store = new MemoryStore('local', saved());
    mount(store);
    const css = () => document.getElementById(STYLE_ID)?.textContent ?? '';
    await screen.findByRole('radio', { name: 'Copper' });
    expect(css()).not.toContain('--om-color-accent:');
    await user.click(screen.getByRole('radio', { name: 'Copper' }));
    await waitFor(() => expect(css()).toContain(`--om-color-accent: ${ACCENTS.copper.light}`));
    expect(css()).not.toContain('--om-color-action:');
    await user.click(screen.getByRole('switch', { name: 'Buttons stay signal red' }));
    await waitFor(() => expect(css()).toContain('--om-color-action:'));
    await waitFor(() => expect(store.saved.at(-1)).toMatchObject({ buttonsRed: false }));
  });

  it('shows the look command and undoes the last change', async () => {
    const user = userEvent.setup();
    mount(new MemoryStore('local', saved()));
    const undo = await screen.findByRole('button', { name: 'Undo last change' });
    expect(undo).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Harbor pack' }));
    expect(document.querySelector('.om-cz-cmdline')).toHaveTextContent('onemind look set --pack harbor');
    await user.click(screen.getByRole('button', { name: 'Undo last change' }));
    expect(screen.getByRole('button', { name: 'Harbor pack' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Undo last change' })).toBeDisabled();
  });

  it('says plainly that the light-mode wallpaper has a veil', async () => {
    mount(new MemoryStore('local', saved()));
    expect(await screen.findByText(/in light mode a veil of the page colour sits over the wallpaper/)).toBeInTheDocument();
  });
});
