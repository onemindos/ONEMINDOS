// SPDX-License-Identifier: Apache-2.0
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AddDevice } from './AddDevice';
import { NetworkPage } from './NetworkPage';
import { joinCommands, machineRows, qrModules, secondsLeft } from './logic';
import type { FabricSummary, JoinTicket, MeshView } from './types';

const NOW = Date.parse('2026-11-12T10:00:00Z');
const CA = 'a1'.repeat(32);
// Mesh addresses are Headscale's default range (examples, not a real network).
const mesh: MeshView = {
  mode: 'lan', box: 'box1', control: { state: 'up', checked_at: '2026-11-12T10:00:00Z' }, relay: null,
  nodes: [
    { node_id: 'hub1', name: 'hub', role: 'hub', online: true, state: 'up', path: 'none', mesh_ip: '100.64.0.1' },
    { node_id: 'n1', name: 'node-n1', role: 'worker', online: true, state: 'up', path: 'direct', mesh_ip: '100.64.0.2' },
  ],
  devices: [], names: { lan: ['onemind.local', 'box1.local'], mesh: ['hub.onemind.internal'] },
  apps: [{ app_id: 'vaultwarden', lan: 'https://vaultwarden.box1.local', lan_alias: 'https://vaultwarden.onemind.local', mesh: 'https://vaultwarden.apps.onemind.internal' }],
  https: true, ca_sha256: CA,
};
const fabric: FabricSummary = {
  hub_node_id: 'hub1', counts: { hub: 1, worker: 1, leaf: 0 },
  nodes: [{ node_id: 'n1', hostname: 'mini-pc', role: 'worker', state: 'online', leaf_link: 'up', mesh: { state: 'up', path: 'direct' }, cert_expires_at: null, joined_at: null }],
  joining: [{ join_request_id: 'jr_1', node_id: 'n2', hostname: 'pi5', role: 'leaf', state: 'awaiting_approval', match_code: 'K7-4QX', action_id: 'a-1', created_at: '2026-11-12T09:59:00Z' }],
};
const ticket: JoinTicket = {
  ticket_id: 'tkt_1', role: 'worker', expires_at: '2026-11-12T10:15:00Z', hub_ca_sha256: CA, hub_url: 'https://box1.local',
  qr_payload: `onemind-join:v1?code=7KQ4-M2XP-9D3F&ca=${CA}&role=worker&hub=https%3A%2F%2Fbox1.local`,
  one_time: { join_code: '7KQ4-M2XP-9D3F' },
};

describe('logic', () => {
  it('encodes the join payload as a square QR matrix', () => {
    const m = qrModules(ticket.qr_payload);
    expect(m.length).toBeGreaterThanOrEqual(41); // a 130-character payload needs version 6+ at level M
    expect(m.every((r) => r.length === m.length)).toBe(true);
    expect(m[0]?.slice(0, 7)).toEqual([1, 1, 1, 1, 1, 1, 1]); // finder pattern, top left
    expect(qrModules('a')).not.toEqual(m);
  });
  it('counts down and quotes the commands', () => {
    expect(secondsLeft(ticket.expires_at, NOW)).toBe(900);
    expect(secondsLeft(ticket.expires_at, NOW + 10_000_000)).toBe(0);
    expect(joinCommands(ticket).install).toBe(`sudo deploy/install.sh --role node --join '${ticket.qr_payload}'`);
  });
  it('makes one row per machine, hub first', () => {
    const rows = machineRows(mesh, fabric);
    expect(rows.map((r) => [r.name, r.role, r.status, r.path])).toEqual([
      ['box1', 'hub', 'online', 'none'], ['mini-pc', 'worker', 'online', 'direct'],
    ]);
  });
});

describe('NetworkPage', () => {
  const base = { now: NOW, onAddDevice: () => {}, onRetry: () => {} };
  it('shows machines and names but no address by default', () => {
    const { container } = render(<NetworkPage {...base} isOwner mesh={{ state: 'ok', data: mesh }} fabric={{ state: 'ok', data: fabric }} />);
    expect(screen.getByText('mini-pc')).toBeTruthy();
    expect(screen.getByText('vaultwarden.box1.local')).toBeTruthy();
    expect(container.textContent).not.toMatch(/100\.64\./);
    expect(screen.getByText(/wants to join/)).toBeTruthy();
  });
  it('reveals addresses only on the owner toggle', () => {
    const onShow = vi.fn();
    const { container } = render(<NetworkPage {...base} isOwner onShowAddresses={onShow} mesh={{ state: 'ok', data: mesh }} fabric={{ state: 'ok', data: fabric }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Show addresses' }));
    expect(onShow).toHaveBeenCalledWith(true);
    expect(container.textContent).toMatch(/100\.64\.0\.2/);
  });
  it('has no address toggle for others', () => {
    render(<NetworkPage {...base} isOwner={false} mesh={{ state: 'ok', data: mesh }} fabric={{ state: 'ok', data: fabric }} />);
    expect(screen.queryByRole('button', { name: 'Show addresses' })).toBeNull();
  });
  it('says when data is old and blocks adding devices', () => {
    render(<NetworkPage {...base} isOwner mesh={{ state: 'ok', data: mesh, staleSince: '2026-11-12T09:50:00Z' }} fabric={{ state: 'ok', data: fabric }} />);
    expect(screen.getByText(/last known/)).toBeTruthy();
    expect((screen.getByRole('button', { name: /Add a device/ }) as HTMLButtonElement).disabled).toBe(true);
  });
  it('offers a retry on error', () => {
    const onRetry = vi.fn();
    render(<NetworkPage {...base} onRetry={onRetry} isOwner mesh={{ state: 'error', message: 'unavailable' }} fabric={{ state: 'ok', data: fabric }} />);
    fireEvent.click(screen.getByRole('button', { name: /Try again/ }));
    expect(onRetry).toHaveBeenCalled();
  });
});

describe('AddDevice', () => {
  it('makes a ticket, shows the QR and the code, and routes approval to Approvals', async () => {
    const createTicket = vi.fn().mockResolvedValue(ticket);
    const onReview = vi.fn();
    render(<AddDevice open onClose={() => {}} mode="lan" createTicket={createTicket} fabric={fabric} onReview={onReview} now={NOW} />);
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /runs apps/ })); });
    expect(createTicket).toHaveBeenCalledWith('worker');
    expect(screen.getByRole('img', { name: /Join code 7KQ4-M2XP-9D3F/ })).toBeTruthy();
    expect(screen.getByText('Valid 15:00')).toBeTruthy();
    expect(screen.getByText(/--role node --join/).textContent).toContain(ticket.qr_payload);
    const waiting = screen.getByRole('heading', { name: 'Requests to join' }).parentElement as HTMLElement;
    fireEvent.click(within(waiting).getByRole('button', { name: /approve/i }));
    expect(onReview).toHaveBeenCalledWith('a-1');
  });
  it('explains phones in home-network mode instead of making a code', () => {
    const createTicket = vi.fn();
    render(<AddDevice open onClose={() => {}} mode="lan" createTicket={createTicket} fabric={null} onReview={() => {}} now={NOW} />);
    fireEvent.click(screen.getByRole('button', { name: /phone or laptop/ }));
    expect(screen.getByText(/needs a relay or a public name/)).toBeTruthy();
    expect(createTicket).not.toHaveBeenCalled();
  });
  it('reports a failed ticket', async () => {
    const createTicket = vi.fn().mockRejectedValue(new Error('permission_denied'));
    render(<AddDevice open onClose={() => {}} mode="lan" createTicket={createTicket} fabric={null} onReview={() => {}} now={NOW} />);
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /small or remote/ })); });
    expect(screen.getByRole('alert').textContent).toContain('permission_denied');
  });
});
