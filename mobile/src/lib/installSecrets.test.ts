// SPDX-License-Identifier: Apache-2.0
import { Features, OP } from '../api/client';
import { makeActions } from '../api/fixtures';
import { ApiError, type AppSecrets } from '../api/types';
import { v0Api } from '../test/fakes';
import { compactValues, formProblems, generatedCount, installAppId, ownerKeys, sealInstallSecrets, secretsToAsk, valueProblem } from './installSecrets';

const SECRETS: AppSecrets = {
  app_id: 'ollama', key_id: 'k1', missing_required: ['ollama-auth/API_KEY'],
  secrets: [{
    name: 'ollama-auth', description: 'Auth', keys: [
      { key: 'API_KEY', kind: 'api-key', description: 'Provider key', required: true, source: 'owner', set: false, version: null, updated_at: null },
      { key: 'HOOK_URL', kind: 'url', description: '', required: false, source: 'owner', set: false, version: null, updated_at: null },
      { key: 'SESSION', kind: 'token', description: '', required: false, source: 'generated', set: false, version: null, updated_at: null },
    ],
  }],
};
const install = makeActions(Date.now())[0]!;
const both = new Features([OP.appSecrets, OP.secretsPublicKey], 'openapi');

describe('install secrets rules', () => {
  it('asks only for owner keys, says how many the box makes', () => {
    expect(ownerKeys(SECRETS).map((k) => k.key.key)).toEqual(['API_KEY', 'HOOK_URL']);
    expect(generatedCount(SECRETS)).toBe(1);
    expect(installAppId(install)).toBe('ollama');
    expect(installAppId({ type: 'app.remove', params: { app_id: 'ollama' } })).toBeUndefined();
  });

  it('checks values like the gateway and never repeats them', () => {
    expect(valueProblem('api-key', 'abc')).toMatch(/4 to 8192/);
    expect(valueProblem('api-key', 'ab cd')).toMatch(/spaces/);
    expect(valueProblem('password', 'ab cd')).toBeUndefined();
    expect(valueProblem('url', 'hostonly')).toMatch(/full URL/);
    expect(valueProblem('url', 'https://h:1/p')).toBeUndefined();
    expect(formProblems(SECRETS, {})).toEqual({ 'ollama-auth/API_KEY': 'Required to install.' });
    const p = formProblems(SECRETS, { 'ollama-auth': { API_KEY: 'sk-secret-1', HOOK_URL: 'nope' } });
    expect(Object.keys(p)).toEqual(['ollama-auth/HOOK_URL']);
    expect(JSON.stringify(p)).not.toContain('sk-secret-1');
  });

  it('seals only typed values for declared owner keys', () => {
    expect(compactValues(SECRETS, { 'ollama-auth': { API_KEY: 'sk-1', HOOK_URL: '', SESSION: 'x' }, other: { Z: 'y' } }))
      .toEqual({ 'ollama-auth': { API_KEY: 'sk-1' } });
  });

  it('refuses to seal when the hub key changed since the form was read', async () => {
    const api = v0Api({ secretsPublicKey: async () => ({ alg: 'X25519', key: 'AAAA', key_id: 'k2', sealed_alg: 'X25519-AES256GCM' }) });
    await expect(sealInstallSecrets(api, SECRETS, { 'ollama-auth': { API_KEY: 'sk-1234' } })).rejects.toThrow(/sealing key changed/);
  });

  it('opens the form only for an install whose app needs owner-typed values on a hub that seals', async () => {
    const appSecrets = jest.fn(async () => SECRETS);
    const api = v0Api({ appSecrets, secretsPublicKey: jest.fn() });
    await expect(secretsToAsk(api, both, install)).resolves.toBe(SECRETS);
    await expect(secretsToAsk(api, new Features([OP.appSecrets], 'openapi'), install)).resolves.toBeUndefined();
    await expect(secretsToAsk(api, both, { ...install, type: 'app.start' })).resolves.toBeUndefined();
    expect(appSecrets).toHaveBeenCalledTimes(1);
    const generatedOnly = { ...SECRETS, secrets: [{ ...SECRETS.secrets[0]!, keys: [SECRETS.secrets[0]!.keys[2]!] }] };
    await expect(secretsToAsk(v0Api({ appSecrets: async () => generatedOnly }), both, install)).resolves.toBeUndefined();
    await expect(secretsToAsk(v0Api({ appSecrets: async () => { throw new ApiError(404, 'not_found', 'gone'); } }), both, install)).resolves.toBeUndefined();
    await expect(secretsToAsk(v0Api({ appSecrets: async () => { throw new ApiError(503, 'unavailable', 'down'); } }), both, install)).rejects.toThrow('down');
  });
});
