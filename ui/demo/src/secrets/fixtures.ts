// SPDX-License-Identifier: Apache-2.0
// Fixtures for the secrets demo and tests: shapes of GET /v1/apps/{id}/secrets and
// GET /v1/apps/{id}/owner-override. No value appears anywhere: the hub never returns one.
import type { AppSecrets, OwnerOverrideInfo } from '../../../src/secrets/types';

export const HERMES = { id: 'hermes-agent', name: 'Hermes Agent' };
export const VAULT = { id: 'vault-like', name: 'Vault-like app' };

const provider = (key: string, description: string) => ({
  key,
  kind: 'api-key' as const,
  description,
  required: false,
  source: 'owner' as const,
  set: false,
  version: null,
  updated_at: null,
});

/** apps/hermes-agent before install: nothing set yet. */
export const hermesSecrets: AppSecrets = {
  app_id: 'hermes-agent',
  key_id: 'sk_3f9c2a1b7d4e5a60',
  missing_required: [],
  secrets: [
    {
      name: 'hermes-agent-credentials',
      description: "Model-provider keys. Enter the key of the provider you use, then pick the model in Hermes's dashboard.",
      keys: [
        provider('OPENROUTER_API_KEY', 'OpenRouter API key (openrouter.ai/keys)'),
        provider('ANTHROPIC_API_KEY', 'Anthropic API key'),
        provider('OPENAI_API_KEY', 'OpenAI API key'),
        {
          key: 'OPENAI_BASE_URL',
          kind: 'url',
          description: 'Optional OpenAI-compatible endpoint; Hermes uses it only with the openai-api provider',
          required: false,
          source: 'owner',
          set: false,
          version: null,
          updated_at: null,
        },
      ],
    },
  ],
};

/** An installed app with a required key, an optional one and a generated one, all set. */
export const vaultSecrets: AppSecrets = {
  app_id: 'vault-like',
  key_id: 'sk_3f9c2a1b7d4e5a60',
  missing_required: [],
  secrets: [
    {
      name: 'vault-like-credentials',
      description: 'Keys the app needs',
      keys: [
        { key: 'PROVIDER_API_KEY', kind: 'api-key', description: 'Model provider key', required: true, source: 'owner', set: true, version: 2, updated_at: '2026-11-12T09:00:00Z' },
        { key: 'PROVIDER_BASE_URL', kind: 'url', description: 'Custom endpoint', required: false, source: 'owner', set: false, version: null, updated_at: null },
        { key: 'ADMIN_PASSWORD', kind: 'password', description: 'Optional admin password', required: false, source: 'owner', set: true, version: 1, updated_at: '2026-11-10T09:00:00Z' },
      ],
    },
    {
      name: 'vault-like-internal',
      description: '',
      keys: [{ key: 'SESSION_SECRET', kind: 'token', description: 'Signs sessions', required: false, source: 'generated', set: true, version: 1, updated_at: '2026-11-10T09:00:00Z' }],
    },
  ],
};

/** The same app before install, with its required key missing. */
export const vaultBeforeInstall: AppSecrets = {
  ...vaultSecrets,
  missing_required: ['vault-like-credentials/PROVIDER_API_KEY'],
  secrets: vaultSecrets.secrets.map((s) => ({ ...s, keys: s.keys.map((k) => ({ ...k, set: false, version: null, updated_at: null })) })),
};

const base: OwnerOverrideInfo = {
  app_id: 'hermes-agent',
  enabled: true,
  scan_problem: "app 'hermes-agent' failed its last scan (2026-11-12T08:01:00Z)",
  eligible: true,
  refusal: null,
  confirm: 'hermes-agent',
  reason_length: [10, 500],
  step_up: 'none',
  requester_must_be: 'person',
};

export const overrideOn = base;
export const overrideOff: OwnerOverrideInfo = { ...base, enabled: false, eligible: false };
export const overrideMalware: OwnerOverrideInfo = {
  ...base,
  eligible: false,
  refusal: "the scan of 'hermes-agent' found malware; an owner override never covers malware",
};
export const overridePasskey: OwnerOverrideInfo = { ...base, step_up: 'passkey' };
export const OVERRIDE_MARK = 'owner override: Upstream fix is not released yet; the box is on my home network only';
