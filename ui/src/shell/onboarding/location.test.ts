// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { formatLocation, locationProblem, parseLocation, siteAnchors, siteIdFor } from './location';

describe('parseLocation (offline, on this device)', () => {
  it.each([
    ['40.7128, -74.0060', 40.7128, -74.006, 'typed'],
    ['40.7128 -74.0060', 40.7128, -74.006, 'typed'],
    ['(51.50809; -0.12804)', 51.50809, -0.12804, 'typed'],
    ['40.7128° N, 74.0060° W', 40.7128, -74.006, 'typed'],
    ['33.8688 S 151.2093 E', -33.8688, 151.2093, 'typed'],
    ['geo:48.8584,2.2945?z=17', 48.8584, 2.2945, 'link'],
    ['https://maps.example/place/x/@35.6586,139.7454,17z/data', 35.6586, 139.7454, 'link'],
    ['https://maps.example/?ll=52.5163,13.3777&z=15', 52.5163, 13.3777, 'link'],
    ['https://maps.example/?q=-22.9519,-43.2105', -22.9519, -43.2105, 'link'],
    ['https://www.openstreetmap.org/#map=17/41.8902/12.4922', 41.8902, 12.4922, 'link'],
    ['https://www.openstreetmap.org/?mlat=59.3293&mlon=18.0686', 59.3293, 18.0686, 'link'],
  ])('reads %s', (input, lat, lon, source) => {
    expect(parseLocation(input)).toEqual({ lat, lon, source });
  });

  it.each([
    '12 Orchard Lane, Springfield',
    'https://maps.example/place/Some+Street',
    '',
    '91, 10',
    '10, 181',
    '0, 0',
    '89.5, 10',
  ])('cannot place %j offline', (input) => {
    expect(parseLocation(input)).toBeNull();
  });
});

describe('locationProblem', () => {
  it('mirrors the gateway checks and refuses grids at the poles', () => {
    expect(locationProblem(40.7, -74)).toBeNull();
    expect(locationProblem(0, 0)).toMatch(/0, 0/);
    expect(locationProblem(Number.NaN, 1)).toMatch(/numbers/);
    expect(locationProblem(-91, 1)).toMatch(/-90 to 90/);
    expect(locationProblem(10, 200)).toMatch(/-180 to 180/);
    expect(locationProblem(86, 10)).toMatch(/pole/);
  });
});

describe('siteAnchors', () => {
  it('puts the place at 0,0 with points 100 m east and north that span two dimensions', () => {
    const [origin, east, north] = siteAnchors({ lat: 40.7128, lon: -74.006 });
    expect(origin).toEqual({ x: 0, y: 0, lat: 40.7128, lon: -74.006 });
    expect(east).toMatchObject({ x: 100, y: 0, lat: 40.7128 });
    expect(north).toMatchObject({ x: 0, y: 100, lon: -74.006 });
    // 100 m north is about 0.0009° of latitude; east is wider in degrees by 1/cos(lat).
    expect(north!.lat - 40.7128).toBeCloseTo(0.0008993, 6);
    expect(east!.lon + 74.006).toBeCloseTo(0.0008993 / Math.cos((40.7128 * Math.PI) / 180), 6);
  });

  it('wraps across the date line', () => {
    const [, east] = siteAnchors({ lat: 10, lon: 179.9995 });
    expect(east!.lon).toBeLessThan(-179.999);
  });
});

it('formats to five decimals with hemispheres and makes a site ID core accepts', () => {
  expect(formatLocation({ lat: -33.8688, lon: 151.2093 })).toBe('33.86880° S, 151.20930° E');
  expect(siteIdFor('Rivera Home')).toBe('rivera-home');
  expect(siteIdFor('Café Ñandú')).toBe('cafe-nandu');
  expect(siteIdFor('  !!  ')).toBe('home');
  expect(siteIdFor('x'.repeat(80))).toMatch(/^[a-z0-9][a-z0-9_-]{0,63}$/);
});
