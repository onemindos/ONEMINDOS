// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useRef, useState } from 'react';
import { animate, useReducedMotion } from '../../motion';

export function SetupMap({ boxName, timeZone, ready }: { boxName: string; timeZone: string; ready: boolean }) {
  const [play, setPlay] = useState(0);
  const reduced = useReducedMotion();
  const map = useRef<SVGSVGElement>(null);
  const clipId = useId();
  useEffect(() => {
    if (!play || !map.current) return;
    const animations = [...map.current.querySelectorAll('[data-map-draw]')].map((path, order) =>
      animate(path, [{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }], {
        duration: 240, delay: order * 50, fill: 'backwards', easing: 'ease-out',
      }, reduced),
    );
    const ring = map.current.querySelector('[data-map-ring]');
    if (ring) animations.push(animate(ring, [{ opacity: 0 }, { opacity: 1 }], { duration: 240, delay: 200, fill: 'backwards' }, reduced));
    return () => animations.forEach((animation) => animation?.cancel());
  }, [play, reduced]);

  return (
    <figure className="oms-setup-map">
      <svg ref={map} aria-hidden="true" viewBox="0 0 320 160" fill="none">
        <defs><clipPath id={clipId}><rect width="320" height="160" rx="16" /></clipPath></defs>
        <g clipPath={`url(#${clipId})`}>
          <path className="oms-setup-map-grid" d="M0 40h320M0 80h320M0 120h320M40 0v160M80 0v160M120 0v160M160 0v160M200 0v160M240 0v160M280 0v160" />
          <g className="oms-setup-map-contours">
            <path data-map-draw="" pathLength="1" d="M-10 114C52 139 70 30 132 38s64 72 117 54 57-85 93-56" />
            <path data-map-draw="" pathLength="1" d="M-14 128C50 158 77 45 128 51s66 79 124 56 60-94 92-60" />
            <path data-map-draw="" pathLength="1" d="M-20 142C53 172 82 58 128 65s68 76 127 52 60-89 89-58" />
            <path data-map-draw="" pathLength="1" d="M-24 155C52 185 93 74 128 79s66 69 131 50 62-87 85-62" />
          </g>
          <circle data-map-ring="" className="oms-setup-map-ring" cx="162" cy="85" r="20" />
          <circle className="oms-setup-map-pin" cx="162" cy="85" r="6" />
        </g>
      </svg>
      <figcaption>
        <span>Asset map preview, planned</span>
        <strong>{boxName || 'Your box'}</strong>
        <span>{timeZone.replaceAll('_', ' ')}</span>
      </figcaption>
      {ready && <button type="button" className="om-btn om-btn-ghost" onClick={() => setPlay((run) => run + 1)}>
        {play ? 'Replay' : 'Draw my map'}
      </button>}
    </figure>
  );
}
