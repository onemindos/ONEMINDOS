// SPDX-License-Identifier: Apache-2.0
// "Where is your place?": the owner types their address and the setup map moves there.
// Sovereignty rule (founder, 2026-11-28): offline first, no outside account, the owner's own data.
//  1. Offline: coordinates or a pasted map link are read on this device (location.ts). The box has no
//     address index yet, so a street address alone cannot be placed; the screen says so plainly.
//  2. The owner enters the coordinates, or asks this device for its position. That second path is the
//     browser's own permission prompt; the screen says the browser may ask its maker's location
//     service. OneMind itself sends the address nowhere and adds no online lookup.
//  3. Skippable: without a position the Map starts with no place, and one can be drawn later.
import { useId, useState } from 'react';
import { cx } from '../../lib/cx';
import { ShellIcon } from '../icons';
import { formatLocation, locationProblem, parseLocation, type PlaceLocation } from './location';

/** Said next to the device-location button, and read out with it. */
export const DEVICE_DISCLOSURE = 'Your browser asks first. Most browsers send nearby Wi-Fi networks and your IP address to an online location service (Google, Apple or Microsoft) to work this out. OneMind does not.';

/** One line, no control characters or bidirectional overrides: what the gateway accepts as an address. */
export function cleanAddress(text: string): string {
  // eslint-disable-next-line no-control-regex -- removing control characters is the point
  return text.replace(/[\u0000-\u001f\u007f]+/g, ' ').replace(/[\u202a-\u202e\u2066-\u2069]/g, '');
}

export interface AddressStepProps {
  address: string;
  location?: PlaceLocation;
  onChange: (patch: { address?: string; location?: PlaceLocation }) => void;
  /** Whether this device can be asked for its position (a secure page with the Geolocation API). */
  deviceLocation?: () => Promise<{ lat: number; lon: number }>;
}

/** The browser's own position, when the page may ask for it (HTTPS or localhost). */
export function browserLocation(): AddressStepProps['deviceLocation'] {
  if (typeof window === 'undefined' || !window.isSecureContext || !('geolocation' in navigator)) return undefined;
  return () => new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(
    (p) => resolve({ lat: p.coords.latitude, lon: p.coords.longitude }),
    (e) => reject(new Error(e.code === e.PERMISSION_DENIED ? 'You did not allow this device to share its location.' : 'This device could not find its location.')),
    { enableHighAccuracy: true, timeout: 15_000, maximumAge: 60_000 },
  ));
}

export function AddressStep({ address, location, onChange, deviceLocation }: AddressStepProps) {
  const ids = { address: useId(), coords: useId(), status: useId(), device: useId() };
  const [coords, setCoords] = useState(location ? `${location.lat}, ${location.lon}` : '');
  const [note, setNote] = useState<{ tone: 'ok' | 'warn' | 'bad'; text: string }>();
  const [asking, setAsking] = useState(false);

  const place = (where: PlaceLocation) => {
    onChange({ location: where });
    setCoords(`${where.lat}, ${where.lon}`);
    setNote({ tone: 'ok', text: `Your map moved to ${formatLocation(where)}.` });
  };

  const find = () => {
    // A pasted link or coordinates in the address box count too: read on this device, never opened.
    const fromAddress = parseLocation(address);
    if (fromAddress) return place(fromAddress);
    if (address.trim()) {
      setNote({ tone: 'warn', text: 'This box has no address index yet, so it cannot turn a street address into a position by itself. Nothing was sent anywhere. Enter the coordinates below, or ask this device.' });
    } else setNote({ tone: 'warn', text: 'Type your address first, or enter coordinates below.' });
  };

  const applyCoords = () => {
    const parsed = parseLocation(coords);
    if (parsed) return place(parsed);
    const [a, b] = coords.split(/[,;\s]+/).map(Number);
    setNote({ tone: 'bad', text: (a !== undefined && b !== undefined && locationProblem(a, b)) || 'Write it as latitude, longitude, for example 40.7128, -74.0060.' });
  };

  return (
    <>
      <div className="oms-field">
        <label htmlFor={ids.address} className="oms-label">Your address</label>
        <div className="oms-input-row">
          <input id={ids.address} className="oms-input" value={address} maxLength={256} autoComplete="street-address"
            placeholder="12 Orchard Lane, Springfield" aria-describedby={`${ids.address}-msg`}
            onChange={(e) => onChange({ address: cleanAddress(e.target.value) })}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); find(); } }} />
          <button type="button" className="om-btn om-btn-secondary" onClick={find}><ShellIcon name="search" size={16} /> Find it on this box</button>
        </div>
        <p id={`${ids.address}-msg`} className="oms-field-hint">Kept on this box as the place’s address. OneMind never sends it to an outside service.</p>
      </div>

      <div className="oms-field">
        <label htmlFor={ids.coords} className="oms-label">Coordinates</label>
        <div className="oms-input-row">
          <input id={ids.coords} className="oms-input" value={coords} inputMode="text" autoComplete="off" spellCheck={false}
            placeholder="40.7128, -74.0060" aria-describedby={`${ids.coords}-msg`}
            onChange={(e) => setCoords(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); applyCoords(); } }} />
          <button type="button" className="om-btn om-btn-secondary" onClick={applyCoords}><ShellIcon name="globe" size={16} /> Move my map here</button>
        </div>
        <p id={`${ids.coords}-msg`} className="oms-field-hint">Latitude, longitude. A link copied from a map app works too: the numbers are read here, the link is not opened.</p>
      </div>

      {deviceLocation && (
        <div className="oms-device-loc">
          <button type="button" className="om-btn om-btn-ghost" aria-describedby={ids.device} aria-busy={asking || undefined} disabled={asking} onClick={async () => {
            setAsking(true);
            try {
              const p = await deviceLocation();
              const problem = locationProblem(p.lat, p.lon);
              if (problem) setNote({ tone: 'bad', text: problem });
              else place({ lat: Number(p.lat.toFixed(6)), lon: Number(p.lon.toFixed(6)), source: 'device' });
            } catch (e) {
              setNote({ tone: 'bad', text: e instanceof Error ? e.message : 'This device could not find its location.' });
            } finally {
              setAsking(false);
            }
          }}>
            <ShellIcon name="nodes" size={16} /> {asking ? 'Asking this device…' : 'Use this device’s location'}
          </button>
          <p id={ids.device} className="oms-field-hint">{DEVICE_DISCLOSURE}</p>
        </div>
      )}

      <div id={ids.status} role="status">
        {note && <p className={cx('oms-note', `om-tone-${note.tone}`)}><ShellIcon name={note.tone === 'ok' ? 'check' : 'alert'} size={16} /> {note.text}</p>}
      </div>
      {location && (
        <button type="button" className="oms-linkbtn" onClick={() => { onChange({ location: undefined }); setCoords(''); setNote(undefined); }}>
          Clear the position
        </button>
      )}
      <p className="om-hint">Optional. Skip it and the Map starts without a place; you can draw it later.</p>
    </>
  );
}
