// SPDX-License-Identifier: Apache-2.0
// First-run wizard (ONB-P1, PU-05): name the box, create the owner with a passkey, choose the
// look, pick starter apps by category, choose where backups go and save the emergency kit
// (cannot be skipped, ONB-B2), then a summary with the headless twin (`onemind init`, ONB-B1).
// Full-screen, no navigation; each step has one heading that receives focus.
import { useEffect, useId, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { cx } from '../lib/cx';
import { applyTheme, type ThemeChoice } from '../lib/theme';
import { dark, light } from '../tokens/tokens';
import { BrandMark, BRAND } from '../components/BrandMark';
import { StatusPill } from '../components/StatusPill';
import { ShellIcon, type ShellIconName } from './icons';
import { CATEGORY_ORDER, category, deployClass, deployClassLabel, type CategorySlug } from './taxonomy';
import {
  ACCENT_IDS,
  accentName,
  accentVars,
  categoryCounts,
  emptyDraft,
  finishRequests,
  furthestReachable,
  initCommand,
  offerable,
  ONBOARDING_STEPS,
  selectedMemoryMb,
  slugifyBoxName,
  stepIssues,
  toggleApp,
  validateBoxName,
  type BackupDestination,
  type OnboardingDraft,
  type StarterApp,
} from './firstRun';
import './shell.css';

export interface OnboardingProps {
  apps: StarterApp[];
  initial?: Partial<OnboardingDraft>;
  /** Start on a given step index (demo and screenshots). */
  initialStep?: number;
  /** Time zones to offer; defaults to the browser's list. */
  timeZones?: string[];
  /** Hub facts shown honestly while choosing apps and backups. */
  hub?: { freeMemoryMb: number; usbDisk?: string };
  /** WebAuthn registration (SEC-P1). Resolves true when the passkey is saved. */
  onCreatePasskey?: () => Promise<boolean>;
  onDownloadKit?: () => void;
  onThemeChange?: (t: ThemeChoice) => void;
  onRestore?: () => void;
  onFinish: (draft: OnboardingDraft, requests: ReturnType<typeof finishRequests>) => void;
}

function zones(): string[] {
  try {
    const f = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf;
    if (f) return f('timeZone');
  } catch {
    /* older engines */
  }
  return ['UTC', 'Europe/London', 'Europe/Berlin', 'America/New_York', 'America/Chicago', 'America/Los_Angeles', 'Asia/Tokyo', 'Australia/Sydney'];
}

const mb = (n: number) => (n >= 1024 ? `${(n / 1024).toFixed(1)} GB` : `${n} MB`);

export function AppGlyph({ name, slug, size = 40 }: { name: string; slug: string; size?: number }) {
  const cat = category(slug);
  return (
    <span className={cx('oms-glyph', `oms-glyph-${slug}`)} style={{ width: size, height: size, fontSize: size * 0.42 }} aria-hidden="true">
      {name[0]}
      {cat && (
        <span className="oms-glyph-cat">
          <ShellIcon name={cat.icon} size={12} />
        </span>
      )}
    </span>
  );
}

function Field({ label, hint, error, children, id }: { label: string; hint?: ReactNode; error?: string | null; children: ReactNode; id: string }) {
  return (
    <div className={cx('oms-field', error && 'oms-field-bad')}>
      <label htmlFor={id} className="oms-label">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-msg`} className="oms-field-msg">
          <ShellIcon name="alert" size={14} /> {error}
        </p>
      ) : (
        hint && (
          <p id={`${id}-msg`} className="oms-field-hint">
            {hint}
          </p>
        )
      )}
    </div>
  );
}

function ThemeThumb({ t }: { t: ThemeChoice }) {
  const half = (th: typeof light) => (
    <>
      <span className="oms-thumb-bar" style={{ background: th.surface, borderColor: th.border }} />
      <span className="oms-thumb-card" style={{ background: th.surface, borderColor: th.border }}>
        <span style={{ background: th.text }} />
        <span style={{ background: th['text-subtle'] }} />
        <span className="oms-thumb-btn" style={{ background: 'var(--om-color-accent)' }} />
      </span>
    </>
  );
  if (t === 'system') {
    return (
      <span className="oms-thumb oms-thumb-split" aria-hidden="true">
        <span className="oms-thumb-half" style={{ background: light.bg }}>
          {half(light)}
        </span>
        <span className="oms-thumb-half" style={{ background: dark.bg }}>
          {half(dark)}
        </span>
      </span>
    );
  }
  const th = t === 'dark' ? dark : light;
  return (
    <span className="oms-thumb" style={{ background: th.bg }} aria-hidden="true">
      {half(th)}
    </span>
  );
}

const DESTS: Array<{ id: BackupDestination; icon: ShellIconName; title: string; body: string }> = [
  { id: 'usb', icon: 'disk', title: 'USB disk', body: 'Plugged into this box. Fast, and works without the internet.' },
  { id: 'peer', icon: 'nodes', title: 'Another OneMind box', body: 'A friend’s or a second box. Encrypted before it leaves.' },
  { id: 's3', icon: 'cloud', title: 'S3-compatible storage', body: 'Any provider that speaks S3. Encrypted before upload.' },
  { id: 'later', icon: 'clock', title: 'Decide later', body: 'Nothing is backed up until you choose a destination.' },
];

export function Onboarding({
  apps,
  initial,
  initialStep = 0,
  timeZones,
  hub,
  onCreatePasskey = () => new Promise((r) => setTimeout(() => r(true), 700)),
  onDownloadKit,
  onThemeChange = applyTheme,
  onRestore,
  onFinish,
}: OnboardingProps) {
  const [d, setD] = useState<OnboardingDraft>(() => ({ ...emptyDraft(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'), ...initial }));
  const [step, setStep] = useState(initialStep);
  const [tried, setTried] = useState(false);
  const [kitDownloaded, setKitDownloaded] = useState(!!initial?.backup?.kitSaved);
  const [cat, setCat] = useState<CategorySlug | 'all'>('all');
  const heading = useRef<HTMLHeadingElement>(null);
  const first = useRef(true);
  const ids = { name: useId(), tz: useId(), owner: useId(), kit: useId(), issues: useId() };
  const tzList = useMemo(() => timeZones ?? zones(), [timeZones]);
  const offer = useMemo(() => offerable(apps), [apps]);

  const s = ONBOARDING_STEPS[step]!;
  const issues = stepIssues(s.id, d);
  const reach = furthestReachable(d);
  const set = (patch: Partial<OnboardingDraft>) => setD((x) => ({ ...x, ...patch }));

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    heading.current?.focus();
    setTried(false);
  }, [step]);

  const next = (e?: FormEvent) => {
    e?.preventDefault();
    if (issues.length) {
      setTried(true);
      return;
    }
    if (s.id === 'done') onFinish(d, finishRequests(d));
    else setStep((i) => Math.min(i + 1, ONBOARDING_STEPS.length - 1));
  };

  const pct = Math.round((step / (ONBOARDING_STEPS.length - 1)) * 100);
  const nameErr = d.boxName || tried ? validateBoxName(d.boxName) : null;

  const body = (() => {
    switch (s.id) {
      case 'box':
        return (
          <>
            <Field id={ids.name} label="Box name" error={nameErr} hint={<>People on your network open it at <strong>{(d.boxName || 'your-name') + '.local'}</strong></>}>
              <div className="oms-input-wrap">
                <ShellIcon name="box" size={18} />
                <input
                  id={ids.name}
                  className="oms-input"
                  value={d.boxName}
                  placeholder="home-hub"
                  autoComplete="off"
                  spellCheck={false}
                  aria-invalid={!!nameErr}
                  aria-describedby={`${ids.name}-msg`}
                  onChange={(e) => set({ boxName: e.target.value.toLowerCase().replace(/\s+/g, '-') })}
                  onBlur={(e) => {
                    if (validateBoxName(e.target.value)) set({ boxName: slugifyBoxName(e.target.value) });
                  }}
                />
                <span className="oms-input-suffix">.local</span>
              </div>
            </Field>
            <div className="oms-suggest" role="group" aria-label="Suggestions">
              {['home-hub', 'family-box', 'workshop'].map((n) => (
                <button key={n} type="button" className="oms-chip" aria-pressed={d.boxName === n} onClick={() => set({ boxName: n })}>
                  {n}
                </button>
              ))}
            </div>
            <Field id={ids.tz} label="Time zone" hint="Backups, updates and quiet hours follow this clock.">
              <select id={ids.tz} className="oms-input oms-select" value={d.timeZone} aria-describedby={`${ids.tz}-msg`} onChange={(e) => set({ timeZone: e.target.value })}>
                {!tzList.includes(d.timeZone) && <option value={d.timeZone}>{d.timeZone}</option>}
                {tzList.map((z) => (
                  <option key={z} value={z}>
                    {z.replace(/_/g, ' ')}
                  </option>
                ))}
              </select>
            </Field>
            {onRestore && (
              <button type="button" className="oms-linkbtn" onClick={onRestore}>
                <ShellIcon name="backups" size={16} /> Moving from another OneMind? Restore from a backup instead
              </button>
            )}
          </>
        );
      case 'owner':
        return (
          <>
            <Field id={ids.owner} label="Your name" error={tried && !d.ownerName.trim() ? 'Enter your name.' : null} hint="Shown on Home and next to every approval you make.">
              <input
                id={ids.owner}
                className="oms-input"
                value={d.ownerName}
                autoComplete="name"
                placeholder="Dana"
                maxLength={64}
                aria-describedby={`${ids.owner}-msg`}
                onChange={(e) => set({ ownerName: e.target.value })}
              />
            </Field>
            <div className={cx('oms-passkey', d.passkey === 'registered' && 'oms-passkey-done', d.passkey === 'failed' && 'oms-passkey-bad')}>
              <span className="oms-passkey-icon">
                <ShellIcon name={d.passkey === 'registered' ? 'check' : 'passkey'} size={28} />
              </span>
              <div className="oms-passkey-text">
                <p className="oms-passkey-title">{d.passkey === 'registered' ? 'Passkey saved' : 'Sign in with a passkey'}</p>
                <p className="om-hint">
                  {d.passkey === 'registered'
                    ? 'You are the owner. Only you can approve changes. Add a second device later in Settings.'
                    : 'Your device unlock (fingerprint, face or PIN) or a security key proves it is you. There is no password to leak or forget.'}
                </p>
                {d.passkey === 'failed' && <p className="oms-field-msg">The passkey was not saved. Try again, or use a security key.</p>}
              </div>
              {d.passkey !== 'registered' && (
                <button
                  type="button"
                  className="om-btn om-btn-primary"
                  aria-busy={d.passkey === 'waiting' || undefined}
                  disabled={d.passkey === 'waiting'}
                  onClick={async () => {
                    set({ passkey: 'waiting' });
                    const ok = await onCreatePasskey().catch(() => false);
                    set({ passkey: ok ? 'registered' : 'failed' });
                  }}
                >
                  {d.passkey === 'waiting' ? <span className="om-spinner" aria-hidden="true" /> : <ShellIcon name="passkey" size={18} />}
                  {d.passkey === 'waiting' ? 'Waiting for your device…' : 'Create passkey'}
                </button>
              )}
            </div>
            <ul className="oms-facts-list">
              <li>
                <ShellIcon name="approvals" size={16} /> Agents and family members can ask for changes. Only the owner approves.
              </li>
              <li>
                <ShellIcon name="lock" size={16} /> Lost every device? The emergency kit you save in step 5 recovers the owner.
              </li>
            </ul>
          </>
        );
      case 'appearance':
        return (
          <>
            <fieldset className="oms-fieldset">
              <legend className="oms-label">Theme</legend>
              <div className="oms-theme-cards">
                {(['system', 'light', 'dark'] as ThemeChoice[]).map((t) => (
                  <label key={t} className={cx('oms-theme-card', d.theme === t && 'oms-on')}>
                    <input
                      type="radio"
                      name="oms-theme"
                      value={t}
                      checked={d.theme === t}
                      onChange={() => {
                        set({ theme: t });
                        onThemeChange(t);
                      }}
                    />
                    <ThemeThumb t={t} />
                    <span className="oms-theme-name">{t === 'system' ? 'Match device' : t === 'light' ? 'Light' : 'Dark'}</span>
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset className="oms-fieldset">
              <legend className="oms-label">Accent colour</legend>
              <div className="oms-swatches">
                {ACCENT_IDS.map((a) => (
                  <label key={a} className={cx('oms-swatch', d.accent === a && 'oms-on')} style={accentVars(a)}>
                    <input type="radio" name="oms-accent" value={a} checked={d.accent === a} onChange={() => set({ accent: a })} />
                    <span className="oms-swatch-dot" aria-hidden="true">
                      {d.accent === a && <ShellIcon name="check" size={16} />}
                    </span>
                    <span className="oms-swatch-name">{accentName(a)}</span>
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="oms-preview" aria-label="Preview" role="group">
              <div className="oms-preview-head">
                <span className="oms-preview-dot" />
                <strong>{d.boxName || 'home-hub'}</strong>
                <StatusPill tone="ok" label="Online" />
              </div>
              <p className="om-hint">Good evening{d.ownerName.trim() ? `, ${d.ownerName.trim()}` : ''}. Everything is running.</p>
              <div className="oms-preview-row">
                <span className="om-btn om-btn-primary om-btn-sm" aria-hidden="true">
                  Approve
                </span>
                <span className="om-btn om-btn-secondary om-btn-sm" aria-hidden="true">
                  Deny
                </span>
                <a href="#preview" tabIndex={-1} onClick={(e) => e.preventDefault()} aria-hidden="true">
                  See details
                </a>
              </div>
            </div>
            <p className="om-hint">Change these any time in Settings → Appearance. Contrast is checked for every accent in light and dark.</p>
          </>
        );
      case 'apps': {
        const counts = categoryCounts(offer, CATEGORY_ORDER);
        const list = cat === 'all' ? offer : offer.filter((a) => a.category === cat);
        const rec = cat === 'all' ? list.filter((a) => a.recommended) : [];
        const rest = cat === 'all' ? list.filter((a) => !a.recommended) : list;
        const used = selectedMemoryMb(offer, d.starterApps);
        const over = hub ? used > hub.freeMemoryMb : false;
        const card = (a: StarterApp) => {
          const on = d.starterApps.includes(a.id);
          const cls = deployClass(a.deployClass);
          return (
            <li key={a.id}>
              <label className={cx('oms-app', on && 'oms-on')}>
                <input type="checkbox" checked={on} onChange={() => set({ starterApps: toggleApp(d.starterApps, a.id) })} />
                <AppGlyph name={a.name} slug={a.category} />
                <span className="oms-app-text">
                  <span className="oms-app-name">{a.name}</span>
                  <span className="oms-app-tag">{a.tagline}</span>
                  <span className="oms-app-meta">
                    <StatusPill tone={cls.tone} label={deployClassLabel(a.deployClass, a.plugin)} dot={false} />
                    <span>{mb(a.minMemoryMb)}</span>
                  </span>
                </span>
                <span className="oms-check" aria-hidden="true">
                  <ShellIcon name="check" size={16} />
                </span>
              </label>
            </li>
          );
        };
        return (
          <>
            <div className="oms-cats" role="group" aria-label="Categories">
              <button type="button" className="oms-chip" aria-pressed={cat === 'all'} onClick={() => setCat('all')}>
                <ShellIcon name="apps" size={16} /> All <span className="oms-chip-n">{offer.length}</span>
              </button>
              {counts.map(({ slug, count }) => {
                const c = category(slug)!;
                return (
                  <button key={slug} type="button" className="oms-chip" aria-pressed={cat === slug} onClick={() => setCat(slug)}>
                    <ShellIcon name={c.icon} size={16} /> {c.name} <span className="oms-chip-n">{count}</span>
                  </button>
                );
              })}
            </div>
            {rec.length > 0 && (
              <section aria-labelledby={`${ids.issues}-rec`} className="oms-app-sec">
                <h2 id={`${ids.issues}-rec`} className="oms-sec-title">
                  <ShellIcon name="agent" size={16} /> Recommended for this box
                </h2>
                <ul className="oms-apps">{rec.map(card)}</ul>
              </section>
            )}
            <section aria-labelledby={`${ids.issues}-all`} className="oms-app-sec">
              <h2 id={`${ids.issues}-all`} className="oms-sec-title">
                {cat === 'all' ? 'More apps' : category(cat)!.name}
              </h2>
              <ul className="oms-apps">{rest.map(card)}</ul>
            </section>
            <div className={cx('oms-tray', over ? 'om-tone-warn' : 'om-tone-neutral')} role="status">
              <ShellIcon name={over ? 'alert' : 'approvals'} size={18} />
              <span>
                {d.starterApps.length === 0 ? (
                  'None picked yet. You can add apps from the Market any time.'
                ) : (
                  <>
                    <strong>
                      {d.starterApps.length} {d.starterApps.length === 1 ? 'app' : 'apps'}
                    </strong>{' '}
                    · about {mb(used)} memory{hub ? ` of ${mb(hub.freeMemoryMb)} free` : ''}. {over ? 'More than the hub has free: some will wait for another node.' : 'Each becomes an install request you approve on Home.'}
                  </>
                )}
              </span>
            </div>
          </>
        );
      }
      case 'backups':
        return (
          <>
            <fieldset className="oms-fieldset">
              <legend className="oms-label">Where should backups go?</legend>
              <div className="oms-dests">
                {DESTS.map((x) => (
                  <label key={x.id} className={cx('oms-dest', d.backup.destination === x.id && 'oms-on', x.id === 'later' && 'oms-dest-later')}>
                    <input type="radio" name="oms-dest" value={x.id} checked={d.backup.destination === x.id} onChange={() => set({ backup: { ...d.backup, destination: x.id } })} />
                    <span className="oms-dest-icon">
                      <ShellIcon name={x.icon} size={20} />
                    </span>
                    <span className="oms-dest-text">
                      <span className="oms-dest-title">{x.title}</span>
                      <span className="oms-dest-body">{x.id === 'usb' && hub?.usbDisk ? `Found: ${hub.usbDisk}. ${x.body}` : x.body}</span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            {d.backup.destination === 'later' && (
              <p className="oms-note om-tone-warn">
                <ShellIcon name="alert" size={16} /> Until you choose, a disk failure loses your data. Home will remind you.
              </p>
            )}
            <section className="oms-kit" aria-labelledby={`${ids.kit}-t`}>
              <div className="oms-kit-art" aria-hidden="true">
                <ShellIcon name="key" size={30} />
              </div>
              <div className="oms-kit-text">
                <h2 id={`${ids.kit}-t`} className="oms-kit-title">
                  Emergency kit <span className="oms-req">Required</span>
                </h2>
                <p className="om-hint">
                  One page with your <strong>owner recovery key</strong> and <strong>backup key</strong>. If this box dies or you lose every device, it is the only way back in. OneMind cannot recover it for you.
                </p>
                <div className="oms-kit-actions">
                  <button
                    type="button"
                    className={cx('om-btn', kitDownloaded ? 'om-btn-secondary' : 'om-btn-primary')}
                    onClick={() => {
                      onDownloadKit?.();
                      setKitDownloaded(true);
                    }}
                  >
                    <ShellIcon name={kitDownloaded ? 'check' : 'download'} size={18} />
                    {kitDownloaded ? 'Downloaded · download again' : 'Download emergency kit (PDF)'}
                  </button>
                </div>
                <label className={cx('oms-confirm', !kitDownloaded && 'oms-confirm-off', tried && !d.backup.kitSaved && 'oms-confirm-bad')}>
                  <input
                    type="checkbox"
                    checked={d.backup.kitSaved}
                    disabled={!kitDownloaded}
                    aria-describedby={`${ids.kit}-why`}
                    onChange={(e) => set({ backup: { ...d.backup, kitSaved: e.target.checked } })}
                  />
                  <span>I printed it or saved it somewhere safe, away from this box.</span>
                </label>
                <p id={`${ids.kit}-why`} className="oms-field-hint">
                  {kitDownloaded ? 'This step cannot be skipped.' : 'Download the kit first. This step cannot be skipped.'}
                </p>
              </div>
            </section>
          </>
        );
      case 'done': {
        const reqs = finishRequests(d);
        return (
          <>
            <div className="oms-done-art" aria-hidden="true">
              <svg viewBox="0 0 160 160" width="132" height="132">
                <circle className="oms-done-ring oms-done-ring-3" cx="80" cy="80" r="76" />
                <circle className="oms-done-ring oms-done-ring-2" cx="80" cy="80" r="58" />
                <circle className="oms-done-core" cx="80" cy="80" r="40" />
                <path className="oms-done-check" d="M62 81l12 12 25-26" />
              </svg>
            </div>
            <dl className="oms-summary">
              <div>
                <dt>Box</dt>
                <dd>
                  <span>
                    <strong>{d.boxName}</strong>.local · {d.timeZone.replace(/_/g, ' ')}
                  </span>
                </dd>
              </div>
              <div>
                <dt>Owner</dt>
                <dd>
                  {d.ownerName.trim()} · <StatusPill tone="ok" label="Passkey saved" />
                </dd>
              </div>
              <div>
                <dt>Look</dt>
                <dd>
                  <span className="oms-mini-swatch" style={accentVars(d.accent)} aria-hidden="true" />
                  {accentName(d.accent)} · {d.theme === 'system' ? 'matches your device' : d.theme}
                </dd>
              </div>
              <div>
                <dt>Backups</dt>
                <dd>
                  {d.backup.destination === 'later' ? <StatusPill tone="warn" label="Not set up" /> : DESTS.find((x) => x.id === d.backup.destination)!.title} · emergency kit saved
                </dd>
              </div>
              <div>
                <dt>Starter apps</dt>
                <dd>{reqs.length === 0 ? 'None. Browse the Market from Home.' : `${reqs.length} install ${reqs.length === 1 ? 'request' : 'requests'} will wait for you on Home`}</dd>
              </div>
            </dl>
            <details className="oms-twin">
              <summary>Set up the next box from a terminal</summary>
              <p className="om-hint">The same steps, headless (planned verb; the passkey step stays interactive):</p>
              <pre className="om-code">
                <code>{initCommand(d)}</code>
              </pre>
            </details>
          </>
        );
      }
    }
  })();

  const lede: Record<(typeof ONBOARDING_STEPS)[number]['id'], string> = {
    box: 'This is how you will find it on your network and on your phone.',
    owner: 'The owner approves every change: installs, updates, restores. Agents can only ask.',
    appearance: 'Pick a theme and an accent. Everyone who signs in can choose their own later.',
    apps: 'Choose a few to start. Nothing is installed yet: each one becomes a request you approve.',
    backups: 'A box without a backup is a box you can lose. Choose a destination and save your keys.',
    done: `${d.boxName || 'Your box'} is ready. Here is what you set up.`,
  };

  return (
    <div className="oms-onb" style={accentVars(d.accent)}>
      <aside className="oms-onb-side" aria-label="Setup progress">
        <div className="oms-onb-brand">
          <BrandMark className="om-brand-mark" />
          <span>
            <span className="oms-onb-brand-name">{BRAND.shortName}</span>
            <span className="oms-onb-brand-sub">Setting up {d.boxName || 'a new box'}</span>
          </span>
        </div>
        <ol className="oms-steps">
          {ONBOARDING_STEPS.map((x, i) => {
            const done = i < step && stepIssues(x.id, d).length === 0;
            const can = i <= Math.max(reach, step) && i !== step;
            return (
              <li key={x.id} className={cx('oms-step', i === step && 'oms-step-on', done && 'oms-step-done')}>
                <button type="button" className="oms-step-btn" aria-current={i === step ? 'step' : undefined} disabled={!can} onClick={() => setStep(i)}>
                  <span className="oms-step-num" aria-hidden="true">
                    {done ? <ShellIcon name="check" size={14} /> : i + 1}
                  </span>
                  <span className="oms-step-name">
                    {x.title}
                    {done && <span className="om-visually-hidden"> (done)</span>}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
        <p className="oms-onb-side-foot">Everything here can also be done with <code>onemind init</code>.</p>
      </aside>
      <div className="oms-onb-main">
        <div className="oms-onb-top">
          <span className="oms-onb-count">
            Step {step + 1} of {ONBOARDING_STEPS.length}
          </span>
          <div className="oms-progress" role="progressbar" aria-label="Setup progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
            <span style={{ width: `${pct}%` }} />
          </div>
        </div>
        <form className="oms-onb-form" onSubmit={next} noValidate key={s.id}>
          <header className="oms-onb-head">
            <h1 ref={heading} tabIndex={-1} className="oms-onb-title">
              {s.id === 'done' ? 'You are all set' : s.title}
            </h1>
            <p className="oms-onb-lede">{lede[s.id]}</p>
          </header>
          <div className="oms-onb-body">{body}</div>
          {tried && issues.length > 0 && (
            <div className="oms-issues om-tone-bad" role="alert" id={ids.issues}>
              <ShellIcon name="alert" size={18} />
              <ul>
                {issues.map((i) => (
                  <li key={i}>{i}</li>
                ))}
              </ul>
            </div>
          )}
          <footer className="oms-onb-foot">
            {step > 0 ? (
              <button type="button" className="om-btn om-btn-ghost" onClick={() => setStep((i) => i - 1)}>
                Back
              </button>
            ) : (
              <span />
            )}
            <button type="submit" className="om-btn om-btn-primary oms-onb-next" aria-describedby={tried && issues.length ? ids.issues : undefined}>
              {s.id === 'done' ? 'Go to Home' : s.id === 'backups' ? 'Finish setup' : 'Continue'}
              <ShellIcon name="arrow" size={18} />
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}
