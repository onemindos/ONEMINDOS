// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ago, approvalsTile, backupsTile, errorText, isInsecureAddress, nodesTile, updatesTile } from '../src/format.js';

const base = { nodes_total: 3, nodes_online: 3, pending: [], updates: null, backups: null };

test('ages', () => {
  assert.equal(ago(100, 105), 'just now');
  assert.equal(ago(100, 145), '45 s ago');
  assert.equal(ago(100, 100 + 180), '3 min ago');
  assert.equal(ago(0), 'not checked yet');
});

test('nodes tile', () => {
  assert.equal(nodesTile(base).tone, 'ok');
  assert.equal(nodesTile({ ...base, nodes_online: 2 }).label, '1 node offline');
});

test('approvals use the agent tone when something waits', () => {
  assert.equal(approvalsTile({ ...base, pending: [{ id: 'a' }] }).tone, 'agent');
});

test('planned routes missing are neutral, never "all good"', () => {
  assert.equal(updatesTile(base).tone, 'neutral');
  assert.equal(backupsTile(base).tone, 'neutral');
});

test('security update is bad tone', () => {
  assert.equal(updatesTile({ ...base, updates: { available: 1, security: true } }).tone, 'bad');
});

test('backup states', () => {
  assert.equal(backupsTile({ ...base, backups: { health: 'not_configured' } }).tone, 'bad');
  assert.equal(backupsTile({ ...base, backups: { health: 'verified' } }).tone, 'ok');
});

test('errors', () => {
  assert.match(errorText('unauthorized'), /token/);
  assert.match(errorText('http_500'), /500/);
});

test('insecure address check mirrors address.rs', () => {
  assert.equal(isInsecureAddress('http://onemind.local:8080'), true);
  assert.equal(isInsecureAddress('http://127.0.0.1:8080'), false);
  assert.equal(isInsecureAddress('http://localhost'), false);
  assert.equal(isInsecureAddress('https://onemind.local'), false);
  assert.equal(isInsecureAddress('onemind.local:8080'), false);
});
