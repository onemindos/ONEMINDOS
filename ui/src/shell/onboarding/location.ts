// SPDX-License-Identifier: Apache-2.0
// Where the owner's place is, worked out on this device only. The box has no address index
// (apps/offline-maps/README.md: "No search box (geocoding)"), so a street address cannot be turned
// into a position offline. What can be: coordinates typed in any common form, or a link copied from
// a map app (the numbers are read out of the text; the link is never opened). Nothing here makes a
// network request, so nobody outside the box learns the address.

export interface PlaceLocation {
  lat: number;
  lon: number;
  /** How the owner gave it, shown on the map so the position is never mistaken for a lookup. */
  source: 'typed' | 'link' | 'device';
}

/** Local grids need a usable east-west direction; past 85° a 100 m step east spans whole degrees. */
const MAX_GRID_LAT = 85;

/** Why a position cannot anchor a site; null when it can. Mirrors core subjects.position_problems. */
export function locationProblem(lat: number, lon: number): string | null {
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return 'Use numbers for latitude and longitude.';
  if (lat < -90 || lat > 90) return 'Latitude runs from -90 to 90.';
  if (lon < -180 || lon > 180) return 'Longitude runs from -180 to 180.';
  // The gateway refuses exactly 0,0; within 0.01° of it the site's own grid points could round onto it.
  if (Math.abs(lat) < 0.01 && Math.abs(lon) < 0.01) return '0, 0 is almost always a missing position, not a real place.';
  if (Math.abs(lat) > MAX_GRID_LAT) return `A local map grid cannot be drawn this close to a pole (above ${MAX_GRID_LAT}°).`;
  return null;
}

const NUM = String.raw`[-+]?\d{1,3}(?:\.\d+)?`;
const signed = (value: string, hemi?: string) => (hemi && /[SWsw]/.test(hemi) ? -Math.abs(Number(value)) : Number(value));

function pair(lat: number, lon: number, source: PlaceLocation['source']): PlaceLocation | null {
  return locationProblem(lat, lon) ? null : { lat, lon, source };
}

/**
 * Reads a position out of what the owner typed or pasted, offline. Understood:
 * "40.7128, -74.0060", "40.7128° N 74.0060° W", "geo:40.7128,-74.006", and map-app links that carry
 * the numbers (".../@40.71,-74.00,17z", "?ll=40.71,-74.00", "?q=40.71,-74.00", "#map=17/40.71/-74.00",
 * "?mlat=40.71&mlon=-74.00"). Anything else (a street address) returns null: there is nothing on the
 * box to look it up with.
 */
export function parseLocation(input: string): PlaceLocation | null {
  const text = input.trim();
  if (!text) return null;
  const isLink = /^(https?:|geo:)/i.test(text);
  const source: PlaceLocation['source'] = isLink ? 'link' : 'typed';
  const patterns: RegExp[] = [
    new RegExp(String.raw`^geo:(${NUM}),(${NUM})`, 'i'),
    new RegExp(String.raw`@(${NUM}),(${NUM})`),
    new RegExp(String.raw`[?&](?:ll|q|query|sll|center)=(${NUM})(?:,|%2C)(${NUM})`, 'i'),
    new RegExp(String.raw`#map=\d{1,2}(?:\.\d+)?/(${NUM})/(${NUM})`),
  ];
  for (const p of patterns) {
    const m = p.exec(text);
    if (m) return pair(Number(m[1]), Number(m[2]), source);
  }
  const mlat = new RegExp(String.raw`[?&]mlat=(${NUM})`).exec(text);
  const mlon = new RegExp(String.raw`[?&]mlon=(${NUM})`).exec(text);
  if (mlat && mlon) return pair(Number(mlat[1]), Number(mlon[1]), source);
  if (isLink) return null;
  // Plain numbers, with optional degree signs and N/S/E/W letters, in latitude-then-longitude order.
  const plain = new RegExp(String.raw`^\(?\s*(${NUM})\s*°?\s*([NSns])?\s*[,;\s]\s*(${NUM})\s*°?\s*([EWew])?\s*\)?$`).exec(text);
  if (plain) return pair(signed(plain[1]!, plain[2]), signed(plain[3]!, plain[4]), source);
  return null;
}

/** "40.71280° N, 74.00600° W": five decimals is about a metre, as precise as a typed address needs. */
export function formatLocation({ lat, lon }: { lat: number; lon: number }): string {
  const f = (v: number, pos: string, neg: string) => `${Math.abs(v).toFixed(5)}° ${v < 0 ? neg : pos}`;
  return `${f(lat, 'N', 'S')}, ${f(lon, 'E', 'W')}`;
}

/** Mean Earth radius (IUGG), metres. Over 100 m the spherical step is off by millimetres. */
const EARTH_M = 6_371_008.8;
const ANCHOR_STEP_M = 100;

const round7 = (v: number) => Math.round(v * 1e7) / 1e7;

/**
 * Three surveyed points for the site's local metre grid (core geo/sites.py needs at least three that
 * span two dimensions): the place itself at 0,0, then 100 m east and 100 m north of it.
 */
export function siteAnchors({ lat, lon }: { lat: number; lon: number }): Array<{ x: number; y: number; lat: number; lon: number }> {
  const dLat = (ANCHOR_STEP_M / EARTH_M) * (180 / Math.PI);
  const dLon = dLat / Math.cos((lat * Math.PI) / 180);
  const wrap = (v: number) => ((((v + 180) % 360) + 360) % 360) - 180;
  return [
    { x: 0, y: 0, lat: round7(lat), lon: round7(lon) },
    { x: ANCHOR_STEP_M, y: 0, lat: round7(lat), lon: round7(wrap(lon + dLon)) },
    { x: 0, y: ANCHOR_STEP_M, lat: round7(lat + dLat), lon: round7(lon) },
  ];
}

/** The site ID core accepts (^[a-z0-9][a-z0-9_-]{0,63}$), from the place name; "home" when none fits. */
export function siteIdFor(placeName: string): string {
  const id = placeName
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ']/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
    .replace(/-+$/, '');
  return id || 'home';
}
