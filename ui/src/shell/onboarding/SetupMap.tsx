// SPDX-License-Identifier: Apache-2.0
// The setup map: it starts empty, and each answer adds one honest thing to it. Naming the place draws
// the survey grid, contours and the box (the signature beat, once per visit; Replay plays it again,
// Escape finishes it). Giving the place a position moves the map there. The approval rule puts a ring
// around the box; picked apps wait under it; a backup choice draws a dashed line out.
// Everything is drawn from props first, then animated, so finishing or skipping a beat shows the same
// picture (HANDBACK O3). Only transform, opacity and stroke-dashoffset move; at most 9 at once.
import { useEffect, useId, useRef, useState } from 'react';
import { animate, useReducedMotion } from '../../motion';
import { formatLocation, type PlaceLocation } from './location';

export interface SetupMapProps {
  boxName: string;
  timeZone: string;
  placeName?: string;
  address?: string;
  location?: PlaceLocation;
  /** The place has been named: the grid, contours and box are on the map. */
  drawn?: boolean;
  /** Bump to play the signature beat (the map draws itself). */
  play?: number;
  /** The approval rule has been seen: the ring around the box. */
  approvals?: boolean;
  /** Install requests waiting for the owner, one tile each (at most 6 drawn). */
  waiting?: number;
  /** A backup destination was chosen (an intention; nothing is backed up yet). */
  backup?: boolean;
  /** Show the Replay control. */
  ready?: boolean;
}

const SOURCE: Record<PlaceLocation['source'], string> = {
  typed: 'from coordinates you typed',
  link: 'from a map link you pasted',
  device: 'from this device’s location',
};

const EASE_DRAW = 'cubic-bezier(.45,0,.2,1)';
const EASE_ENTER = 'cubic-bezier(.2,0,0,1)';

export function SetupMap({ boxName, timeZone, placeName = '', address = '', location, drawn = true, play = 0, approvals = false, waiting = 0, backup = false, ready = false }: SetupMapProps) {
  const [replays, setReplays] = useState(0);
  const reduced = useReducedMotion();
  const map = useRef<SVGSVGElement>(null);
  const clipId = useId();
  const beat = play + replays;
  const where = location ? `${location.lat},${location.lon}` : '';
  const lastWhere = useRef(where);
  const beatRun = useRef<Array<Animation | undefined>>([]);

  // The signature: the grid fades in, four contours draw, the box settles, one ring. Colours stay tokens,
  // so the grid is not revealed through a luminance mask (that would need a literal white).
  useEffect(() => {
    if (!beat || !map.current || !drawn) return;
    const svg = map.current;
    const run: Array<Animation | undefined> = [];
    const grid = svg.querySelector('[data-map-grid]');
    if (grid) run.push(animate(grid, [{ opacity: 0 }, { opacity: 1 }], { duration: 620, easing: EASE_DRAW, fill: 'backwards' }, reduced));
    svg.querySelectorAll('[data-map-draw]').forEach((path, order) => {
      run.push(animate(path, [{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }], { duration: 900, delay: 260 + order * 90, easing: EASE_DRAW, fill: 'backwards' }, reduced));
    });
    const pin = svg.querySelector('[data-map-pin]');
    if (pin) run.push(animate(pin, [{ opacity: 0, transform: 'translateY(-14px)' }, { opacity: 1, transform: 'none' }], { duration: 240, delay: 1000, easing: EASE_ENTER, fill: 'backwards' }, reduced));
    const ring = svg.querySelector('[data-map-ring]');
    if (ring) run.push(animate(ring, [{ opacity: 0 }, { opacity: 1 }], { duration: 240, delay: 1180, fill: 'backwards' }, reduced));
    beatRun.current = run;
    return () => run.forEach((a) => a?.cancel());
  }, [beat, drawn, reduced]);

  // A new position: the whole map slides in from the direction of travel and the box settles on it.
  useEffect(() => {
    if (!map.current || where === lastWhere.current) return;
    const before = lastWhere.current;
    lastWhere.current = where;
    if (!where) return;
    const [lat0, lon0] = before ? before.split(',').map(Number) : [0, 0];
    const [lat1, lon1] = where.split(',').map(Number);
    const angle = Math.atan2((lat1 ?? 0) - (lat0 ?? 0), (lon1 ?? 0) - (lon0 ?? 0));
    const dx = Math.round(Math.cos(angle) * 48);
    const dy = Math.round(-Math.sin(angle) * 48);
    // A position given while the map is still drawing: the drawing finishes first, so at most the two
    // movements below run (the animation cap holds).
    beatRun.current.forEach((a) => a?.finish());
    beatRun.current = [];
    const pan = map.current.querySelector('[data-map-pan]');
    const pin = map.current.querySelector('[data-map-pin]');
    const run = [
      pan && animate(pan, [{ transform: `translate(${dx}px, ${dy}px)`, opacity: 0.4 }, { transform: 'none', opacity: 1 }], { duration: 620, easing: EASE_DRAW }, reduced),
      pin && animate(pin, [{ opacity: 0, transform: 'translateY(-12px)' }, { opacity: 1, transform: 'none' }], { duration: 240, delay: 520, easing: EASE_ENTER, fill: 'backwards' }, reduced),
    ];
    return () => run.forEach((a) => a?.cancel());
  }, [where, reduced]);

  const tiles = Math.min(waiting, 6);
  const facts = [
    drawn && `${boxName || 'Your box'}, this box`,
    location && `${placeName.trim() || 'Your place'} at ${formatLocation(location)}`,
    approvals && 'A ring around the box: AI can ask, only you approve',
    waiting > 0 && `${waiting} install ${waiting === 1 ? 'request' : 'requests'} waiting for you`,
    backup && 'Backups: a destination chosen, not set up yet',
  ].filter((x): x is string => !!x);

  return (
    <figure className="oms-setup-map" data-drawn={drawn || undefined}>
      <svg ref={map} aria-hidden="true" viewBox="0 0 320 160" fill="none">
        <defs>
          <clipPath id={clipId}><rect width="320" height="160" rx="16" /></clipPath>
        </defs>
        <g clipPath={`url(#${clipId})`}>
          {drawn ? (
            <g data-map-pan="">
              <path data-map-grid="" className="oms-setup-map-grid" d="M0 40h320M0 80h320M0 120h320M40 0v160M80 0v160M120 0v160M160 0v160M200 0v160M240 0v160M280 0v160" />
              <g className="oms-setup-map-contours">
                <path data-map-draw="" pathLength="1" d="M-10 114C52 139 70 30 132 38s64 72 117 54 57-85 93-56" />
                <path data-map-draw="" pathLength="1" d="M-14 128C50 158 77 45 128 51s66 79 124 56 60-94 92-60" />
                <path data-map-draw="" pathLength="1" d="M-20 142C53 172 82 58 128 65s68 76 127 52 60-89 89-58" />
                <path data-map-draw="" pathLength="1" d="M-24 155C52 185 93 74 128 79s66 69 131 50 62-87 85-62" />
              </g>
              {backup && <g className="oms-setup-map-backup"><path d="M168 85H262" /><rect x="262" y="77" width="16" height="16" rx="3" /></g>}
              {approvals && <circle className="oms-setup-map-gate" cx="162" cy="85" r="32" />}
              <circle data-map-ring="" className="oms-setup-map-ring" cx="162" cy="85" r="20" />
              <circle data-map-pin="" className="oms-setup-map-pin" cx="162" cy="85" r="6" />
              {Array.from({ length: tiles }, (_, i) => (
                <rect key={i} className="oms-setup-map-tile" x={162 - (tiles * 12 - 4) / 2 + i * 12} y="124" width="8" height="8" rx="2" />
              ))}
            </g>
          ) : (
            <circle className="oms-setup-map-empty" cx="162" cy="85" r="5" />
          )}
        </g>
      </svg>
      <figcaption>
        <span>Asset map preview, planned</span>
        <strong>{placeName.trim() || boxName || 'Your map starts empty'}</strong>
        {address.trim() && <span>{address.trim()}</span>}
        {location ? <span>{formatLocation(location)} · {SOURCE[location.source]}</span> : <span>{timeZone.replaceAll('_', ' ')}</span>}
      </figcaption>
      {facts.length > 0 && (
        <ul className="om-visually-hidden" aria-label="On your map">
          {facts.map((f) => <li key={f}>{f}</li>)}
        </ul>
      )}
      {ready && drawn && <button type="button" className="om-btn om-btn-ghost" onClick={() => setReplays((run) => run + 1)}>
        {beat ? 'Replay' : 'Draw my map'}
      </button>}
    </figure>
  );
}
