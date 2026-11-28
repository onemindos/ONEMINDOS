// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { useNavigate } from 'react-router';
import { Icon } from '@onemind/ui';
import { COMPACT_WINDOWS, parentPath } from '../DesktopShell';
import { ScreenRoutes, routeFor } from './ScreenRoutes';
import { useKeymap } from '../keys/useKeymap';
import { SnapFlyout } from './SnapFlyout';
import { WORKSPACES, type DesktopWindow, type Rect } from './store';
import { SNAP_LAYOUTS, snapRect } from './tiling';
import './snap.css';

const HOVER_OPEN_MS = 350;
const HOVER_CLOSE_MS = 250;
const HALVES = SNAP_LAYOUTS[0]!.zones;
/** On the focused maximise button (a menu button, not a global shortcut), the down arrow opens snap layouts. */
const OPENS_SNAP: ReadonlySet<string> = new Set(['ArrowDown']);

const edges = ['n', 'ne', 'e', 'se', 's', 'sw', 'w', 'nw'] as const;
type Handle = 'move' | typeof edges[number];
function adjust(rect: Rect, handle: Handle, dx: number, dy: number): Rect {
  if (handle === 'move') return { ...rect, x: rect.x + dx, y: rect.y + dy };
  const left = handle.includes('w') ? Math.max(0, Math.min(rect.x + dx, rect.x + rect.width - 25)) : rect.x;
  const top = handle.includes('n') ? Math.max(0, Math.min(rect.y + dy, rect.y + rect.height - 20)) : rect.y;
  const right = Math.min(100, rect.x + rect.width + (handle.includes('e') ? dx : 0));
  const bottom = Math.min(100, rect.y + rect.height + (handle.includes('s') ? dy : 0));
  return { x: left, y: top, width: right - left, height: bottom - top };
}

interface Props {
  item: DesktopWindow;
  z: number;
  active: boolean;
  narrow: boolean;
  /** False when the window lives on another workspace. */
  here: boolean;
  /** Where tiling puts this window, when tiling is on. */
  tile?: Rect;
  onSend(workspace: number): void;
  onPosition(rect: Rect): void;
  onMax(): void;
  onClose(): void;
  onMinimise(): void;
}
export function WindowFrame({ item, z, active, narrow, here, tile, onSend, onPosition, onMax, onClose, onMinimise }: Props) {
  const navigate = useNavigate();
  const label = useId();
  const frame = useRef<HTMLElement>(null);
  const drag = useRef<{ handle: Handle; rect: Rect; x: number; y: number; width: number; height: number } | null>(null);
  const { id, path, rect, maximised, ws } = item;
  const { title, icon } = routeFor(path)!.screen;
  // Snap layouts (Atlas 01b): only for a free window on a wide screen (tiling and phones place windows themselves).
  const canSnap = !narrow && !tile;
  const snapId = useId();
  const maxButton = useRef<HTMLButtonElement>(null);
  const [snap, setSnap] = useState<{ keyboard: boolean } | null>(null);
  const hover = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(hover.current), []);
  const later = (fn: () => void, ms: number) => { window.clearTimeout(hover.current); hover.current = window.setTimeout(fn, ms); };
  function snapTo(r: Rect) {
    setSnap(null);
    onPosition(r);
  }
  function closeSnap(refocus: boolean) {
    setSnap(null);
    if (refocus) maxButton.current?.focus();
  }
  useKeymap({
    'snap-left': () => (active && here && canSnap ? snapTo(HALVES[0]!.rect) : false),
    'snap-right': () => (active && here && canSnap ? snapTo(HALVES[1]!.rect) : false),
  });
  const up = parentPath(path.split(/[?#]/)[0]!);
  function pointerDown(e: PointerEvent<HTMLButtonElement>, handle: Handle) {
    if (e.button !== 0 || narrow || maximised || tile) return;
    const stage = frame.current?.parentElement?.getBoundingClientRect();
    if (!stage?.width || !stage.height) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { handle, rect, x: e.clientX, y: e.clientY, width: stage.width, height: stage.height };
  }
  function pointerMove(e: PointerEvent<HTMLButtonElement>) {
    const d = drag.current;
    if (d && e.currentTarget.hasPointerCapture(e.pointerId)) {
      onPosition(adjust(d.rect, d.handle, (e.clientX - d.x) * 100 / d.width, (e.clientY - d.y) * 100 / d.height));
    }
  }
  function arrow(e: KeyboardEvent<HTMLButtonElement>, handle: Handle) {
    const movement: Record<string, [number, number]> = { ArrowLeft: [-2, 0], ArrowRight: [2, 0], ArrowUp: [0, -2], ArrowDown: [0, 2] };
    const delta = movement[e.key];
    if (delta && !maximised && !tile) { e.preventDefault(); onPosition(adjust(rect, handle, ...delta)); }
  }
  // Releasing a drag at the left or right screen edge snaps the window to that half (always on).
  function pointerUp(e: PointerEvent<HTMLButtonElement>, handle: Handle) {
    const stage = frame.current?.parentElement?.getBoundingClientRect();
    if (handle !== 'move' || !drag.current || !stage?.width) return;
    const snapped = snapRect((e.clientX - stage.left) * 100 / stage.width);
    if (snapped) onPosition(snapped);
  }
  const interaction = (handle: Handle) => ({
    onPointerDown: (e: PointerEvent<HTMLButtonElement>) => pointerDown(e, handle),
    onPointerMove: pointerMove,
    onPointerUp: (e: PointerEvent<HTMLButtonElement>) => pointerUp(e, handle),
    onLostPointerCapture: () => { drag.current = null; },
    onKeyDown: (e: KeyboardEvent<HTMLButtonElement>) => arrow(e, handle),
  });
  const full = maximised || narrow;
  const at = !full && tile ? tile : rect;
  const style = { zIndex: z, left: full ? '0%' : at.x + '%', top: full ? '0%' : at.y + '%', width: full ? '100%' : at.width + '%', height: full ? '100%' : at.height + '%' };
  const activate = () => { if (!active) navigate(path); };
  return <section ref={frame} data-window-id={id} className="dsk-window wm-frame" hidden={item.minimised || !here} data-tiled={!full && tile ? '' : undefined} style={style} aria-labelledby={label}
    data-size={COMPACT_WINDOWS.has(id) ? 'compact' : undefined} onPointerDownCapture={activate} onFocusCapture={activate}>
    <span id={label} className="om-visually-hidden">{title}</span>
    <div className="dsk-window-bar wm-titlebar">
      {up && <button className="dsk-wbtn" aria-label="Back" onClick={() => navigate(up)}><Icon name="chevron" className="dsk-flip" size={18} /></button>}
      {/* The title bar names the window for the eye; assistive tech hears the name once, from the region's label. */}
      <span className="wm-title" aria-hidden="true"><Icon name={icon} size={16} /><span className="wm-title-text">{title}</span></span>
      {!narrow && <button className="wm-move" aria-label={`Move ${title}`} title="Drag or use arrow keys to move. Double-click to maximise." {...interaction('move')} onDoubleClick={onMax} />}
      <button className="dsk-wbtn" aria-label={`Minimise ${title}`} onClick={onMinimise}>−</button>
      {!narrow && <button className="dsk-wbtn wm-send" aria-label={`Workspace ${ws + 1}: Send ${title} to workspace ${(ws + 1) % WORKSPACES + 1}`} title={`On workspace ${ws + 1}. Send to the next one (Alt Shift 1 to 4 picks directly)`} onClick={() => onSend((ws + 1) % WORKSPACES)}>{ws + 1}</button>}
      {!narrow && (
        <span className="wm-maxwrap" onPointerEnter={() => canSnap && later(() => setSnap((s) => s ?? { keyboard: false }), HOVER_OPEN_MS)} onPointerLeave={() => later(() => setSnap((s) => (s?.keyboard ? s : null)), HOVER_CLOSE_MS)}
          onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setSnap(null); }}>
          <button ref={maxButton} className="dsk-wbtn" aria-label={`${maximised ? 'Restore' : 'Maximise'} ${title}`} onClick={onMax}
            title={canSnap ? 'Maximise. Hover or press the down arrow for snap layouts.' : undefined}
            aria-expanded={canSnap ? !!snap : undefined} aria-controls={canSnap && snap ? snapId : undefined}
            onKeyDown={(e) => { if (OPENS_SNAP.has(e.key) && canSnap) { e.preventDefault(); setSnap({ keyboard: true }); } }}>□</button>
          {canSnap && snap && <SnapFlyout id={snapId} title={title} focusFirst={snap.keyboard} onSnap={snapTo} onClose={closeSnap} />}
        </span>
      )}
      <button className="dsk-wbtn dsk-close" aria-label={`Close ${title}`} onClick={onClose}><Icon name="x" size={18} /></button>
    </div>
    <div inert={!active} aria-hidden={!active || undefined} tabIndex={0} className="dsk-window-body">
      <ScreenRoutes location={path} />
    </div>
    {!full && edges.map(edge => <button key={edge} className="wm-edge" data-edge={edge} aria-label={`Resize ${title} (${edge.toUpperCase()})`} {...interaction(edge)} />)}
  </section>;
}
