// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { describe, expect, it, vi } from 'vitest';
import { HERMES, OVERRIDE_MARK, VAULT, hermesSecrets, overrideMalware, overrideOff, overrideOn, overridePasskey, vaultBeforeInstall, vaultSecrets } from '../../demo/src/secrets/fixtures';
import { approveBody, overrideProblems, submissionProblems, valueProblem } from './logic';
import { OwnerOverrideDialog, OwnerOverrideMark } from './OwnerOverride';
import { SecretsForm } from './SecretsForm';

async function noAxeViolations(el: Element) {
  const res = await axe.run(el, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
  expect(res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(', ')}`)).toEqual([]);
}

describe('logic', () => {
  it('mirrors the gateway value rules without quoting values', () => {
    expect(valueProblem('api-key', 'abc')).toMatch(/4 to 8192/);
    expect(valueProblem('api-key', 'has space')).toMatch(/spaces/);
    expect(valueProblem('password', 'has space ok')).toBeUndefined();
    expect(valueProblem('token', 'line\nbreak')).toMatch(/line breaks/);
    expect(valueProblem('url', 'example.com')).toMatch(/full URL/);
    expect(valueProblem('url', 'http://127.0.0.1:11434/v1')).toBeUndefined();
    expect(valueProblem('api-key', 'secret-value with space')).not.toContain('secret-value');
  });

  it('needs required keys at install and some change in change mode', () => {
    expect(submissionProblems(vaultBeforeInstall, { values: {}, generate: [], clear: [] }, 'install')).toEqual({
      'vault-like-credentials/PROVIDER_API_KEY': 'Required to install.',
    });
    expect(submissionProblems(vaultSecrets, { values: {}, generate: [], clear: [] }, 'install')).toEqual({});
    expect(submissionProblems(vaultSecrets, { values: {}, generate: [], clear: [] }, 'change')._form).toMatch(/Rotate or Clear/);
    expect(submissionProblems(vaultSecrets, { values: {}, generate: ['vault-like-internal/SESSION_SECRET'], clear: [] }, 'change')).toEqual({});
  });

  it('builds the approve body only from what is present', () => {
    expect(approveBody({})).toBeUndefined();
    expect(approveBody({ override: { reason: 'r', confirm: 'c' } })).toEqual({ override: { reason: 'r', confirm: 'c' } });
    expect(overrideProblems(overrideOn, '  too   short ', 'hermes-agent').reason).toBeTruthy();
    expect(overrideProblems(overrideOn, 'a sufficiently long reason', 'Hermes-Agent').confirm).toBeTruthy();
    expect(overrideProblems(overrideOn, 'a sufficiently long reason', 'hermes-agent')).toEqual({ reason: undefined, confirm: undefined });
  });
});

describe('SecretsForm', () => {
  it('lists Hermes keys masked, with kinds, and passes axe', async () => {
    const { container } = render(<SecretsForm app={HERMES} secrets={hermesSecrets} mode="install" onSubmit={vi.fn()} />);
    const key = screen.getByLabelText('OPENROUTER_API_KEY');
    expect(key).toHaveAttribute('type', 'password');
    expect(key).toHaveAttribute('autocomplete', 'off');
    expect(screen.getByLabelText('OPENAI_BASE_URL')).toHaveAttribute('type', 'url');
    expect(screen.getAllByText('API key')).toHaveLength(3);
    expect(screen.getByText(/never shown again/)).toBeInTheDocument();
    await noAxeViolations(container);
  });

  it('refuses to submit without a required key and focuses it', async () => {
    const u = userEvent.setup();
    const onSubmit = vi.fn();
    render(<SecretsForm app={VAULT} secrets={vaultBeforeInstall} mode="install" onSubmit={onSubmit} />);
    await u.click(screen.getByRole('button', { name: 'Approve with these secrets' }));
    expect(onSubmit).not.toHaveBeenCalled();
    const field = screen.getByLabelText('PROVIDER_API_KEY');
    expect(field).toHaveFocus();
    expect(field).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Required to install.')).toBeInTheDocument();
  });

  it('hands over only typed values, then forgets them', async () => {
    const u = userEvent.setup();
    const onSubmit = vi.fn();
    render(<SecretsForm app={VAULT} secrets={vaultBeforeInstall} mode="install" onSubmit={onSubmit} />);
    const field = screen.getByLabelText('PROVIDER_API_KEY');
    await u.type(field, 'sk-test-typed-value');
    await u.click(within(field.closest('li')!).getByRole('button', { name: 'Show', pressed: false }));
    expect(field).toHaveAttribute('type', 'text');
    await u.click(screen.getByRole('button', { name: 'Approve with these secrets' }));
    expect(onSubmit).toHaveBeenCalledWith({ values: { 'vault-like-credentials': { PROVIDER_API_KEY: 'sk-test-typed-value' } }, generate: [], clear: [] });
    expect(field).toHaveValue('');
    expect(field).toHaveAttribute('type', 'password');
  });

  it('validates a URL before sealing', async () => {
    const u = userEvent.setup();
    const onSubmit = vi.fn();
    render(<SecretsForm app={VAULT} secrets={vaultSecrets} mode="install" onSubmit={onSubmit} />);
    await u.type(screen.getByLabelText('PROVIDER_BASE_URL'), 'not-a-url');
    await u.click(screen.getByRole('button', { name: 'Approve with these secrets' }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/full URL/)).toBeInTheDocument();
  });

  it('change mode rotates generated keys and clears optional ones, never required ones', async () => {
    const u = userEvent.setup();
    const onSubmit = vi.fn();
    const { container } = render(<SecretsForm app={VAULT} secrets={vaultSecrets} mode="change" onSubmit={onSubmit} />);
    expect(screen.getAllByText('Set').length).toBe(3);
    expect(screen.getAllByRole('checkbox', { name: /Clear/ })).toHaveLength(1); // ADMIN_PASSWORD only
    await u.click(screen.getByRole('button', { name: 'Request this change' }));
    expect(screen.getByRole('alert')).toHaveTextContent(/Rotate or Clear/);
    await u.click(screen.getByRole('checkbox', { name: /Rotate/ }));
    await u.click(screen.getByRole('checkbox', { name: /Clear/ }));
    expect(screen.getByLabelText('ADMIN_PASSWORD')).toBeDisabled();
    await u.click(screen.getByRole('button', { name: 'Request this change' }));
    expect(onSubmit).toHaveBeenCalledWith({ values: {}, generate: ['vault-like-internal/SESSION_SECRET'], clear: ['vault-like-credentials/ADMIN_PASSWORD'] });
    await noAxeViolations(container);
  });

  it('shows the gateway error', () => {
    render(<SecretsForm app={VAULT} secrets={vaultSecrets} mode="install" error="stale_precondition: try again" onSubmit={vi.fn()} />);
    expect(screen.getByRole('alert')).toHaveTextContent('try again');
  });
});

describe('OwnerOverrideDialog', () => {
  it('explains that the override is off and offers nothing else', () => {
    render(<OwnerOverrideDialog open app={HERMES} info={overrideOff} onClose={vi.fn()} onConfirm={vi.fn()} />);
    const dialog = screen.getByRole('dialog', { name: 'Owner override is off' });
    expect(within(dialog).getByText('ONEMIND_ALLOW_OWNER_OVERRIDE=1')).toBeInTheDocument();
    expect(within(dialog).queryByRole('textbox')).toBeNull();
  });

  it('says why malware cannot be overridden', () => {
    render(<OwnerOverrideDialog open app={HERMES} info={overrideMalware} onClose={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.getByText(/never covers malware/)).toBeInTheDocument();
  });

  it('refuses an agent-requested install', () => {
    render(<OwnerOverrideDialog open app={HERMES} info={overrideOn} requestedBy={{ id: 'agent:hermes-agent', kind: 'agent' }} onClose={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.getByText(/only for installs you request yourself/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Override/ })).toBeNull();
  });

  it('needs a reason and the typed app id before it confirms', async () => {
    const u = userEvent.setup();
    const onConfirm = vi.fn();
    render(<OwnerOverrideDialog open app={HERMES} info={overrideOn} requestedBy={{ id: 'owner', kind: 'person' }} onClose={vi.fn()} onConfirm={onConfirm} />);
    const dialog = screen.getByRole('alertdialog', { name: 'Install Hermes Agent despite its scan?' });
    expect(within(dialog).getByText(/failed its last scan/)).toBeInTheDocument();
    const go = within(dialog).getByRole('button', { name: 'Override and install' });
    expect(go).toBeDisabled();
    await u.type(within(dialog).getByLabelText('Why you accept the findings'), 'Fix not released;   LAN only');
    await u.type(within(dialog).getByLabelText(/to confirm/), 'hermes-agen');
    expect(go).toBeDisabled();
    await u.type(within(dialog).getByLabelText(/to confirm/), 't');
    expect(go).toBeEnabled();
    await u.click(go);
    expect(onConfirm).toHaveBeenCalledWith({ reason: 'Fix not released; LAN only', confirm: 'hermes-agent' });
    await noAxeViolations(dialog);
  });

  it('names the passkey step when the owner has one', () => {
    render(<OwnerOverrideDialog open app={HERMES} info={overridePasskey} onClose={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Override with passkey' })).toBeInTheDocument();
    expect(screen.getByText('You confirm with your passkey.')).toBeInTheDocument();
  });

  it('marks an overridden install in red with the reason', () => {
    const { container } = render(<OwnerOverrideMark mark={OVERRIDE_MARK} />);
    expect(container.querySelector('.om-tone-bad')).not.toBeNull();
    expect(screen.getByText('Owner override')).toBeInTheDocument();
    expect(screen.getByText(/Upstream fix is not released yet/)).toBeInTheDocument();
  });
});
