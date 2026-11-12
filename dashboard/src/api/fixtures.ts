// Mock-mode fixtures shaped exactly like contract §2 (heartbeat), §3 (nodes, apps,
// actions) and §4 (app manifest fields). Timestamps are relative to "now" so the
// stale and offline nodes stay stale and offline whenever the demo is opened.
// No real host data: ids, hostnames and models are made up.

import type { Action, CatalogApp, Instance, NodeHeartbeat, NodeRecord, Principal } from './types';

export const DEMO_TOKENS: Record<string, Principal> = {
  'owner-demo': { id: 'owner', kind: 'person', role: 'owner' },
  'adult-demo': { id: 'alex', kind: 'person', role: 'adult' },
  'agent-demo': { id: 'ops-agent', kind: 'agent', role: 'agent' },
};

const iso = (now: number, secondsAgo: number) => new Date(now - secondsAgo * 1000).toISOString();

function hb(over: Partial<NodeHeartbeat> & Pick<NodeHeartbeat, 'node_id' | 'hostname' | 'board' | 'arch'>): NodeHeartbeat {
  return {
    schema: 'onemind.node.status/v1',
    role: 'node',
    os: { id: 'debian', version_id: '13', pretty: 'Debian GNU/Linux 13 (trixie)' },
    kernel: '6.12.0-arm64',
    cpu_model: 'Generic CPU',
    cpus: 4,
    mem_total_mb: 8000,
    mem_available_mb: 5000,
    disk_total_gb: 120,
    disk_free_gb: 80,
    tpm2: false,
    secure_boot: 'unsupported',
    k3s: { present: true, role: 'agent', ready: true },
    rauc: { present: false, booted_slot: null, slots: [] },
    gpu: { nvidia: false, model: null },
    uptime_s: 3600,
    agent_version: '0.1.0',
    observed_at: '',
    ...over,
  };
}

export function makeNodes(now: number): NodeRecord[] {
  const rows: Array<[NodeHeartbeat, NodeRecord['status'], number]> = [
    [
      hb({
        node_id: '3f9c2a1b7d4e',
        hostname: 'hub',
        role: 'hub',
        board: 'x86_64-efi',
        arch: 'amd64',
        kernel: '6.12.0-amd64',
        cpu_model: 'x86-64 mini PC (4 cores)',
        mem_total_mb: 15800,
        mem_available_mb: 9800,
        disk_total_gb: 476.9,
        disk_free_gb: 401.2,
        tpm2: true,
        secure_boot: 'disabled',
        k3s: { present: true, role: 'server', ready: true },
        rauc: { present: true, booted_slot: 'A', slots: [] },
        uptime_s: 86400 * 2 + 3600,
      }),
      'online',
      4,
    ],
    [
      hb({
        node_id: 'a1d07c55e912',
        hostname: 'pi-garage',
        board: 'rpi5',
        arch: 'arm64',
        kernel: '6.12.25-rpi-2712',
        cpu_model: 'Cortex-A76 (4 cores)',
        mem_total_mb: 7900,
        mem_available_mb: 6100,
        disk_total_gb: 119.1,
        disk_free_gb: 97.4,
        uptime_s: 50400,
      }),
      'online',
      7,
    ],
    [
      hb({
        node_id: '7be2f0c4a903',
        hostname: 'orin-lab',
        board: 'jetson-orin',
        arch: 'arm64',
        os: { id: 'ubuntu', version_id: '22.04', pretty: 'Ubuntu 22.04 (NVIDIA L4T)' },
        kernel: '5.15.148-tegra',
        cpu_model: 'Cortex-A78AE (6 cores)',
        cpus: 6,
        mem_total_mb: 7600,
        mem_available_mb: 4200,
        disk_total_gb: 233.0,
        disk_free_gb: 150.8,
        gpu: { nvidia: true, model: 'Orin (Ampere)' },
        uptime_s: 7200,
      }),
      'stale',
      55,
    ],
    [
      hb({
        node_id: 'c4e8019ab6f2',
        hostname: 'cloud-1',
        board: 'vm-do',
        arch: 'amd64',
        kernel: '6.12.0-amd64',
        cpu_model: 'Virtual CPU (2 cores)',
        cpus: 2,
        mem_total_mb: 3900,
        mem_available_mb: 2100,
        disk_total_gb: 78.0,
        disk_free_gb: 61.5,
        secure_boot: 'unknown',
        uptime_s: 604800,
      }),
      'offline',
      14 * 60 + 30,
    ],
  ];
  return rows.map(([h, status, ago]) => ({
    ...h,
    observed_at: iso(now, ago),
    status,
    last_seen: iso(now, ago),
  }));
}

export const INSTANCE: Instance = { name: 'Home OneMind', version: '0.1.0', hub_node_id: '3f9c2a1b7d4e' };

export function makeApps(): CatalogApp[] {
  return [
    {
      id: 'uptime-kuma',
      name: 'Uptime Kuma',
      version: '2.0.2',
      description: 'Self-hosted uptime monitoring',
      category: 'monitoring',
      icon: 'icon.svg',
      license: 'MIT',
      source: 'https://github.com/louislam/uptime-kuma',
      archs: ['amd64', 'arm64'],
      requires: { gpu: false, minMemoryMb: 256 },
      web_port: 3001,
      installed: true,
      status: 'installed',
    },
    {
      id: 'jellyfin',
      name: 'Jellyfin',
      version: '10.10.7',
      description: 'Stream your own films, shows and music',
      category: 'media',
      icon: 'icon.svg',
      license: 'GPL-2.0-only',
      source: 'https://github.com/jellyfin/jellyfin',
      archs: ['amd64', 'arm64'],
      requires: { gpu: false, minMemoryMb: 1024 },
      web_port: 8096,
      installed: false,
      status: 'not_installed',
    },
    {
      id: 'ollama',
      name: 'Ollama',
      version: '0.6.5',
      description: 'Run local AI language models on your own hardware',
      category: 'ai',
      icon: 'icon.svg',
      license: 'MIT',
      source: 'https://github.com/ollama/ollama',
      archs: ['amd64', 'arm64'],
      requires: { gpu: true, minMemoryMb: 4096 },
      web_port: 11434,
      installed: false,
      status: 'not_installed',
    },
  ];
}

export function makeActions(now: number): Action[] {
  return [
    {
      id: 'act-0001',
      type: 'app.install',
      params: { app_id: 'ollama' },
      idempotency_key: '00000000-0000-4000-8000-000000000001',
      expires_at: iso(now, -45 * 60),
      state: 'awaiting_approval',
      requested_by: DEMO_TOKENS['agent-demo'],
      created_at: iso(now, 120),
      updated_at: iso(now, 120),
    },
    {
      id: 'act-0000',
      type: 'app.install',
      params: { app_id: 'uptime-kuma' },
      idempotency_key: '00000000-0000-4000-8000-000000000000',
      expires_at: iso(now, 86400 - 3600),
      state: 'succeeded',
      requested_by: DEMO_TOKENS['owner-demo'],
      decided_by: DEMO_TOKENS['owner-demo'],
      created_at: iso(now, 86400),
      updated_at: iso(now, 86400 - 30),
    },
  ];
}
