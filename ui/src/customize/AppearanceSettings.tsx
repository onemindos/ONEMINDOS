// SPDX-License-Identifier: Apache-2.0
// Settings → Appearance (IA §2.10; parity gap PU-03). Theme, accent, wallpaper, layout, text
// size, corners, motion and transparency, per person. Appearance changes nothing on the box,
// so it is not a request and needs no approval (P1 applies to box state); it is still
// headless-first: every control maps to one field of PUT /v1/me/preferences (§12, pending).
import { useId, useRef, useState, type CSSProperties, type DragEvent, type ReactNode } from 'react';
import { dark, light } from '../tokens/tokens';
import { Button } from '../components/Button';
import { Icon } from '../components/Icon';
import { StatusPill } from '../components/StatusPill';
import { cx } from '../lib/cx';
import { formatAgo, secondsSince } from '../lib/time';
import { ACCENTS, ACCENT_IDS, DEFAULT_ACCENT, presetAccent, type AccentId } from './accents';
import { normalizeHex } from './color';
import { ChoiceGroup, RangeField, SettingRow } from './controls';
import { useCustomize } from './CustomizeProvider';
import {
  DEFAULT_PREFERENCES,
  MAX_BLUR,
  effectiveDim,
  resolveAccent,
  scheduledTheme,
  type AppearancePreferences,
  type Corners,
  type Density,
  type FontScale,
  type MotionPref,
  type ThemeMode,
  type TransparencyPref,
} from './preferences';
import { API_CONTRACT_STATUS, PREFERENCES_PATH } from './store';
import { prepareWallpaper, checkUpload } from './upload';
import { WALLPAPERS, WALLPAPER_IDS, type WallpaperChoice } from './wallpapers';
import { WallpaperSurface, wallpaperLayers } from './WallpaperLayer';

type Vars = CSSProperties & Record<`--${string}`, string>;

/** Variables so a swatch or thumbnail shows its light value in light mode and dark in dark. */
const pair = (name: string, l: string, d: string): Vars => ({ [`--om-cz-${name}-l`]: l, [`--om-cz-${name}-d`]: d }) as Vars;

const pct = (v: number) => `${Math.round(v * 100)} %`;

function Section({ title, description, children, id }: { title: string; description?: ReactNode; children: ReactNode; id?: string }) {
  const hid = useId();
  return (
    <section className="om-cz-section" aria-labelledby={hid} id={id}>
      <header className="om-cz-section-head">
        <h2 id={hid} className="om-cz-section-title">
          {title}
        </h2>
        {description && <p className="om-cz-desc">{description}</p>}
      </header>
      {children}
    </section>
  );
}

/* ------------------------------------------------------------------ status */

export function AppearanceStatus({ onReset }: { onReset?: () => void }) {
  const { status, storeKind, now, retry } = useCustomize();
  const ago = status.updatedAt ? formatAgo(secondsSince(status.updatedAt, now().getTime())) : null;
  let pill: ReactNode;
  if (status.saving) pill = <StatusPill tone="info" label="Saving…" pulse />;
  else if (status.saveError) pill = <StatusPill tone="bad" label="Not saved to your account" />;
  else if (status.stale) pill = <StatusPill tone="warn" label="Not synced" detail={ago ? `local copy from ${ago}` : 'defaults'} />;
  else if (status.source === 'defaults') pill = <StatusPill tone="neutral" label="Defaults" detail="nothing saved yet" />;
  else if (status.source === 'hub') pill = <StatusPill tone="ok" label="Saved to your account" detail={ago ?? undefined} />;
  else pill = <StatusPill tone="neutral" label="Saved on this browser" detail={ago ?? undefined} />;
  return (
    <div className="om-cz-status">
      <div className="om-cz-status-main" role="status" aria-live="polite">
        {pill}
        <span className="om-cz-desc">
          {storeKind === 'local' && !status.stale && 'Only this browser keeps it until your account can store appearance (contract §12, pending).'}
          {status.saveError && ` ${status.saveError}`}
        </span>
      </div>
      {status.stale && (
        <div className="om-cz-banner om-tone-warn" role="note">
          <Icon name="alert" size={18} />
          <span>
            <strong>Not synced with your account.</strong> {status.loadError} You are seeing the copy saved on this browser
            {ago ? ` ${ago}` : ''}; changes stay here until it is back.
          </span>
          <Button size="sm" onClick={retry}>
            Try again
          </Button>
        </div>
      )}
      {onReset && (
        <Button size="sm" variant="ghost" icon="updates" onClick={onReset} className="om-cz-reset">
          Reset to defaults
        </Button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ theme */

function ThemeArt({ mode }: { mode: ThemeMode }) {
  const l = { bg: light.bg, surface: light.surface, line: light.border, accent: light.accent };
  const d = { bg: dark.bg, surface: dark.surface, line: dark.border, accent: dark.accent };
  const win = (t: typeof l) =>
    ({ '--a-bg': t.bg, '--a-surface': t.surface, '--a-line': t.line, '--a-accent': t.accent }) as Vars;
  return (
    <span className={cx('om-cz-theme-art', `om-cz-theme-${mode}`)} aria-hidden="true">
      <span className="om-cz-art-win" style={win(mode === 'dark' ? d : l)}>
        <span className="om-cz-art-side" />
        <span className="om-cz-art-body">
          <span className="om-cz-art-bar" />
          <span className="om-cz-art-bar om-cz-art-bar-short" />
          <span className="om-cz-art-dot" />
        </span>
      </span>
      {(mode === 'system' || mode === 'schedule') && (
        <span className="om-cz-art-win om-cz-art-half" style={win(d)}>
          <span className="om-cz-art-side" />
          <span className="om-cz-art-body">
            <span className="om-cz-art-bar" />
            <span className="om-cz-art-bar om-cz-art-bar-short" />
            <span className="om-cz-art-dot" />
          </span>
        </span>
      )}
      {mode === 'schedule' && (
        <span className="om-cz-art-badge">
          <Icon name="clock" size={14} />
        </span>
      )}
    </span>
  );
}

function ThemeSection() {
  const { prefs, update, now } = useCustomize();
  const sid = useId();
  const current = scheduledTheme(prefs.schedule, now());
  return (
    <Section title="Theme" description="Light, dark, or follow your device. Scheduled switches by the clock on this device.">
      <ChoiceGroup<ThemeMode>
        legend="Theme"
        hideLegend
        variant="cards"
        value={prefs.theme}
        onChange={(theme) => update({ theme })}
        choices={[
          { value: 'system', label: 'Auto', hint: 'Follows your device', visual: <ThemeArt mode="system" /> },
          { value: 'light', label: 'Light', visual: <ThemeArt mode="light" /> },
          { value: 'dark', label: 'Dark', visual: <ThemeArt mode="dark" /> },
          { value: 'schedule', label: 'Scheduled', hint: 'By time of day', visual: <ThemeArt mode="schedule" /> },
        ]}
      />
      {prefs.theme === 'schedule' && (
        <div className="om-cz-schedule" role="group" aria-labelledby={`${sid}-t`}>
          <span id={`${sid}-t`} className="om-visually-hidden">
            Schedule
          </span>
          <label className="om-cz-field">
            <span>
              <Icon name="moon" size={16} /> Dark from
            </span>
            <input type="time" required value={prefs.schedule.darkFrom} onChange={(e) => e.target.value && update({ schedule: { ...prefs.schedule, darkFrom: e.target.value } })} />
          </label>
          <label className="om-cz-field">
            <span>
              <Icon name="sun" size={16} /> Light from
            </span>
            <input type="time" required value={prefs.schedule.lightFrom} onChange={(e) => e.target.value && update({ schedule: { ...prefs.schedule, lightFrom: e.target.value } })} />
          </label>
          <p className="om-cz-desc om-cz-schedule-now">
            Now: <strong>{current === 'dark' ? 'dark' : 'light'}</strong> until {current === 'dark' ? prefs.schedule.lightFrom : prefs.schedule.darkFrom}.
          </p>
        </div>
      )}
    </Section>
  );
}

/* ------------------------------------------------------------------ accent */

function AccentSection() {
  const { prefs, update } = useCustomize();
  const name = useId();
  const [draft, setDraft] = useState<string | null>(null);
  const resolved = resolveAccent(prefs);
  const wpAccent = prefs.wallpaper !== 'none' && prefs.wallpaper !== 'custom' ? WALLPAPERS[prefs.wallpaper].accent : DEFAULT_ACCENT;
  const wp = presetAccent(wpAccent);
  const selected = prefs.accentSource === 'preset' ? prefs.accentPreset : prefs.accentSource;
  const custom = resolveAccent({ ...prefs, accentSource: 'custom' });
  const hexText = draft ?? prefs.accentCustom;
  const hexValid = normalizeHex(hexText) !== null;

  const options: Array<{ value: string; label: string; vars: Vars; hint?: string }> = [
    { value: 'wallpaper', label: 'Match wallpaper', vars: pair('sw', wp.light.set.accent, wp.dark.set.accent), hint: ACCENTS[wpAccent].name },
    ...ACCENT_IDS.map((id: AccentId) => {
      const a = presetAccent(id);
      return { value: id, label: ACCENTS[id].name, vars: pair('sw', a.light.set.accent, a.dark.set.accent) };
    }),
    { value: 'custom', label: 'Custom', vars: pair('sw', custom.light.set.accent, custom.dark.set.accent) },
  ];

  return (
    <Section title="Accent colour" description="Buttons, links and the current page in the menu. Every choice is checked for readable contrast (WCAG AA).">
      <fieldset className="om-cz-group">
        <legend className="om-visually-hidden">Accent colour</legend>
        <div className="om-cz-swatches">
          {options.map((o) => (
            <label key={o.value} className={cx('om-cz-swatch', selected === o.value && 'om-cz-on', o.value === 'wallpaper' && 'om-cz-swatch-wide')}>
              <input
                type="radio"
                name={name}
                value={o.value}
                checked={selected === o.value}
                onChange={() =>
                  o.value === 'wallpaper' || o.value === 'custom' ? update({ accentSource: o.value }) : update({ accentSource: 'preset', accentPreset: o.value as AccentId })
                }
              />
              <span className={cx('om-cz-swatch-dot', o.value === 'custom' && 'om-cz-swatch-custom', o.value === 'wallpaper' && 'om-cz-swatch-wp')} style={o.vars} aria-hidden="true">
                <Icon name="check" size={16} className="om-cz-swatch-check" />
              </span>
              <span className="om-cz-swatch-label">
                {o.label}
                {o.hint && <span className="om-cz-choice-hint">{o.hint}</span>}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      {prefs.accentSource === 'custom' && (
        <div className="om-cz-custom">
          <label className="om-cz-field om-cz-field-color">
            <span>Pick a colour</span>
            <input
              type="color"
              value={normalizeHex(prefs.accentCustom) ?? '#1f6a66'}
              onChange={(e) => {
                setDraft(null);
                update({ accentCustom: e.target.value });
              }}
            />
          </label>
          <label className="om-cz-field">
            <span>Hex</span>
            <input
              type="text"
              inputMode="text"
              spellCheck={false}
              autoComplete="off"
              value={hexText}
              aria-invalid={!hexValid || undefined}
              aria-describedby={`${name}-hex`}
              onChange={(e) => {
                setDraft(e.target.value);
                const n = normalizeHex(e.target.value);
                if (n) update({ accentCustom: n });
              }}
              onBlur={() => setDraft(null)}
            />
          </label>
          <p id={`${name}-hex`} className={cx('om-cz-desc', !hexValid && 'om-cz-error')}>
            {!hexValid ? (
              'Enter a colour like #2a7f62.'
            ) : resolved.light.adjusted || resolved.dark.adjusted ? (
              <>
                Adjusted for readable text: <code>{resolved.light.set.accent}</code> in light ({resolved.light.ratio.toFixed(1)}:1) and <code>{resolved.dark.set.accent}</code> in dark (
                {resolved.dark.ratio.toFixed(1)}:1).
              </>
            ) : (
              <>
                Readable as picked: {resolved.light.ratio.toFixed(1)}:1 in light, {resolved.dark.ratio.toFixed(1)}:1 in dark.
              </>
            )}
          </p>
        </div>
      )}
    </Section>
  );
}

/* ------------------------------------------------------------------ wallpaper */

function WallpaperSection() {
  const { prefs, update, wallpaperImage, setWallpaperImage } = useCustomize();
  const name = useId();
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const acc = resolveAccent(prefs);
  const dl = effectiveDim(prefs, 'light', acc.light.set.accent);
  const dd = effectiveDim(prefs, 'dark', acc.dark.set.accent);
  const floor = Math.max(dl.min, dd.min);
  const none = prefs.wallpaper === 'none';

  async function take(file: File | undefined) {
    if (!file) return;
    setError(null);
    const reason = checkUpload(file);
    if (reason) {
      setError(reason);
      return;
    }
    setBusy(true);
    try {
      const prepared = await prepareWallpaper(file);
      await setWallpaperImage(prepared.dataUrl, prepared.colors);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'That image could not be used.');
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    void take(e.dataTransfer.files[0]);
  };

  const tiles: Array<{ value: WallpaperChoice; label: string; layers: [string, string] | null }> = [
    { value: 'none', label: 'None', layers: null },
    ...WALLPAPER_IDS.map((id) => ({ value: id as WallpaperChoice, label: WALLPAPERS[id].name, layers: wallpaperLayers(id, null) })),
  ];
  const customLayers = wallpaperLayers('custom', wallpaperImage);

  return (
    <Section title="Wallpaper" description="Drawn for OneMind and generated in your browser. Text on top is kept readable: the dim never goes below what contrast needs.">
      <fieldset className="om-cz-group">
        <legend className="om-visually-hidden">Wallpaper</legend>
        <div className="om-cz-wallpapers">
          {tiles.map((t) => (
            <label key={t.value} className={cx('om-cz-wptile', prefs.wallpaper === t.value && 'om-cz-on')}>
              <input type="radio" name={name} value={t.value} checked={prefs.wallpaper === t.value} onChange={() => update({ wallpaper: t.value })} />
              {t.layers ? (
                <WallpaperSurface layers={t.layers} className="om-cz-wptile-art" />
              ) : (
                <span className="om-cz-wptile-art om-cz-wptile-none" aria-hidden="true">
                  <Icon name="x" size={20} />
                </span>
              )}
              <span className="om-cz-wptile-label">{t.label}</span>
            </label>
          ))}
          <label
            className={cx('om-cz-wptile', prefs.wallpaper === 'custom' && 'om-cz-on', dragging && 'om-cz-drop', !customLayers && 'om-cz-wptile-disabled')}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <input type="radio" name={name} value="custom" disabled={!customLayers} checked={prefs.wallpaper === 'custom'} onChange={() => update({ wallpaper: 'custom' })} />
            {customLayers ? (
              <WallpaperSurface layers={customLayers} className="om-cz-wptile-art" />
            ) : (
              <span className="om-cz-wptile-art om-cz-wptile-none" aria-hidden="true">
                <Icon name="plus" size={20} />
              </span>
            )}
            <span className="om-cz-wptile-label">{customLayers ? 'Your image' : 'Your image (none yet)'}</span>
          </label>
        </div>
      </fieldset>
      <div className="om-cz-upload">
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="om-visually-hidden"
          tabIndex={-1}
          aria-hidden="true"
          onChange={(e) => void take(e.target.files?.[0])}
        />
        <Button size="sm" icon="plus" busy={busy} onClick={() => fileRef.current?.click()}>
          {customLayers ? 'Replace your image…' : 'Upload your own…'}
        </Button>
        {customLayers && (
          <Button size="sm" variant="ghost" onClick={() => void setWallpaperImage(null).catch((e: unknown) => setError(e instanceof Error ? e.message : 'Could not remove it.'))}>
            Remove your image
          </Button>
        )}
        <span className="om-cz-desc">JPEG, PNG or WebP up to 10 MB, or drop it on the tile. It is resized to 2560 px in your browser.</span>
        {error && (
          <p className="om-cz-error" role="alert">
            {error}
          </p>
        )}
      </div>
      <div className="om-cz-sliders">
        <RangeField
          label="Blur"
          value={prefs.wallpaperBlur}
          min={0}
          max={MAX_BLUR}
          step={2}
          disabled={none}
          onChange={(wallpaperBlur) => update({ wallpaperBlur })}
          format={(v) => (v === 0 ? 'Off' : `${v} px`)}
        />
        <RangeField
          label="Dim"
          value={prefs.wallpaperDim}
          min={0}
          max={0.95}
          step={0.05}
          floor={none ? undefined : floor}
          disabled={none}
          onChange={(wallpaperDim) => update({ wallpaperDim })}
          format={pct}
          hint={
            none
              ? 'Pick a wallpaper to adjust it.'
              : dl.raised || dd.raised
                ? `Raised for readable text: ${pct(dl.dim)} in light, ${pct(dd.dim)} in dark.`
                : `Readable text needs at least ${pct(dl.min)} in light and ${pct(dd.min)} in dark.`
          }
        />
      </div>
    </Section>
  );
}

/* ------------------------------------------------------------------ layout and effects */

function LayoutSection() {
  const { prefs, update } = useCustomize();
  return (
    <Section title="Layout and text">
      <SettingRow title="Density" description="Compact fits more on a screen; tap targets stay at least 36 px on mouse screens and 44 px on touch.">
        <ChoiceGroup<Density>
          legend="Density"
          hideLegend
          value={prefs.density}
          onChange={(density) => update({ density })}
          choices={[
            { value: 'comfortable', label: 'Comfortable' },
            { value: 'compact', label: 'Compact' },
          ]}
        />
      </SettingRow>
      <SettingRow title="Text size" description="Scales all text and spacing together, on top of your browser's own setting.">
        <ChoiceGroup<FontScale>
          legend="Text size"
          hideLegend
          value={prefs.fontScale}
          onChange={(fontScale) => update({ fontScale })}
          choices={[
            { value: 0.9, label: 'Smaller' },
            { value: 1, label: 'Default' },
            { value: 1.125, label: 'Larger' },
            { value: 1.25, label: 'Largest' },
          ]}
        />
      </SettingRow>
      <SettingRow title="Corners">
        <ChoiceGroup<Corners>
          legend="Corners"
          hideLegend
          value={prefs.corners}
          onChange={(corners) => update({ corners })}
          choices={(['sharp', 'standard', 'round'] as const).map((c) => ({
            value: c,
            label: c === 'sharp' ? 'Sharp' : c === 'standard' ? 'Standard' : 'Round',
            visual: <span className={`om-cz-corner om-cz-corner-${c}`} aria-hidden="true" />,
          }))}
        />
      </SettingRow>
    </Section>
  );
}

function EffectsSection() {
  const { prefs, update } = useCustomize();
  return (
    <Section title="Motion and effects">
      <SettingRow title="Reduce motion" description="Stops sliding, fading and pulsing. Your device's setting is always respected.">
        <ChoiceGroup<MotionPref>
          legend="Reduce motion"
          hideLegend
          value={prefs.motion}
          onChange={(motion) => update({ motion })}
          choices={[
            { value: 'system', label: 'Like my device' },
            { value: 'reduce', label: 'Always' },
          ]}
        />
      </SettingRow>
      <SettingRow title="Transparency" description="Frosted glass on cards and the menu over the wallpaper. Off draws solid surfaces.">
        <ChoiceGroup<TransparencyPref>
          legend="Transparency"
          hideLegend
          value={prefs.transparency}
          onChange={(transparency) => update({ transparency })}
          choices={[
            { value: 'system', label: 'Like my device' },
            { value: 'on', label: 'On' },
            { value: 'off', label: 'Off' },
          ]}
        />
      </SettingRow>
    </Section>
  );
}

/* ------------------------------------------------------------------ preview and API */

export function AppearancePreview() {
  return (
    <section className="om-cz-preview" aria-label="Preview">
      <div className="om-cz-preview-head">
        <span className="om-cz-preview-kicker">Preview</span>
        <StatusPill tone="ok" label="Online" />
      </div>
      <div className="om-cz-preview-card">
        <div className="om-cz-preview-app">
          <span className="om-cz-preview-icon" aria-hidden="true">
            <Icon name="home" size={22} />
          </span>
          <span>
            <strong>Home Assistant</strong>
            <span className="om-cz-desc">Home &amp; IoT · hub</span>
          </span>
        </div>
        <p className="om-cz-preview-text">
          An agent asked to restart it. <a href="#preview">See why</a>
        </p>
        <div className="om-cz-preview-pills">
          <StatusPill tone="agent" label="Agent" dot={false} />
          <StatusPill tone="warn" label="Waiting" />
        </div>
        <div className="om-cz-preview-actions">
          <Button variant="primary" size="sm" tabIndex={-1}>
            Approve
          </Button>
          <Button size="sm" tabIndex={-1}>
            Deny
          </Button>
        </div>
      </div>
    </section>
  );
}

function cliArgs(p: AppearancePreferences): string {
  const d = DEFAULT_PREFERENCES;
  const parts: string[] = [];
  if (p.theme !== d.theme) parts.push(`theme=${p.theme}`);
  if (p.accentSource === 'preset') parts.push(`accent=${p.accentPreset}`);
  else if (p.accentSource === 'custom') parts.push(`accent=${p.accentCustom}`);
  if (p.wallpaper !== d.wallpaper) parts.push(`wallpaper=${p.wallpaper}`);
  if (p.density !== d.density) parts.push(`density=${p.density}`);
  if (p.fontScale !== d.fontScale) parts.push(`font-scale=${p.fontScale}`);
  return parts.join(' ') || 'theme=system';
}

export function AppearanceApiEquivalent() {
  const { prefs } = useCustomize();
  return (
    <details className="om-details om-cz-api">
      <summary>Same change from the API or CLI</summary>
      <p className="om-cz-desc">
        <code>PUT {PREFERENCES_PATH}</code>: {API_CONTRACT_STATUS}. CLI verb planned. Appearance is personal: agents cannot read or change it.
      </p>
      <pre className="om-code">{`PUT ${PREFERENCES_PATH}\n${JSON.stringify({ appearance: prefs }, null, 2)}`}</pre>
      <pre className="om-code">{`onemind me appearance set ${cliArgs(prefs)}   # planned`}</pre>
    </details>
  );
}

/* ------------------------------------------------------------------ the screen body */

function Skeleton() {
  return (
    <div className="om-cz-skeleton" aria-busy="true">
      <span className="om-visually-hidden" role="status">
        Loading your appearance…
      </span>
      {[0, 1, 2].map((i) => (
        <div key={i} className="om-cz-skel-block" aria-hidden="true">
          <span className="om-cz-skel-line om-cz-skel-title" />
          <span className="om-cz-skel-row">
            {[0, 1, 2, 3].map((j) => (
              <span key={j} className="om-cz-skel-tile" />
            ))}
          </span>
        </div>
      ))}
    </div>
  );
}

export function AppearanceSettings() {
  const ctx = useCustomize();
  const [undo, setUndo] = useState<AppearancePreferences | null>(null);
  if (ctx.status.phase === 'loading') return <Skeleton />;
  if (ctx.status.phase === 'error') {
    return (
      <div className="om-cz-banner om-cz-banner-block om-tone-bad" role="alert">
        <Icon name="alert" size={20} />
        <span>
          <strong>Your appearance could not be loaded.</strong> {ctx.status.loadError} The default look is shown; nothing was changed.
        </span>
        <Button size="sm" onClick={ctx.retry}>
          Try again
        </Button>
      </div>
    );
  }
  return (
    <div className="om-cz">
      <AppearanceStatus
        onReset={() => {
          setUndo(ctx.prefs);
          ctx.replace({ ...DEFAULT_PREFERENCES, theme: 'system' });
        }}
      />
      {undo && (
        <div className="om-cz-banner om-tone-info" role="status">
          <Icon name="info" size={18} />
          <span>Appearance reset to defaults.</span>
          <Button
            size="sm"
            onClick={() => {
              ctx.replace(undo);
              setUndo(null);
            }}
          >
            Undo
          </Button>
        </div>
      )}
      <div className="om-cz-layout">
        <div className="om-cz-main">
          <ThemeSection />
          <AccentSection />
          <WallpaperSection />
          <LayoutSection />
          <EffectsSection />
          <AppearanceApiEquivalent />
        </div>
        <aside className="om-cz-aside" aria-label="Live preview">
          <AppearancePreview />
        </aside>
      </div>
    </div>
  );
}
