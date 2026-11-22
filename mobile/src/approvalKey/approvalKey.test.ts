// SPDX-License-Identifier: Apache-2.0
// #703: the phone's approval key. A real P-256 key (noble) stands in for the Keystore; the checks are real.
import type { ApprovalKeyNative } from '../../modules/onemind-approval-key';
import { Features, HttpApi, OP } from '../api/client';
import { makeActions } from '../api/fixtures';
import { ApiError, type Action, type ApproveOptions } from '../api/types';
import { decide } from '../lib/approvals';
import { toB64url } from '../lib/device';
import type { Passkeys } from '../lib/webauthn';
import { v0Api } from '../test/fakes';
import { fakeKey } from './testKey';
import { enrol, forget, loadRecord, makeSigner, pointFromSpki, signingPayload, verifyDeviceSignature, type ApprovalKeyRecord } from '.';

let n = 0;
const challenge = () => `Y2hhbGxlbmdl${++n}`;
const card = (over: Partial<Action> = {}): Action => ({ ...makeActions(Date.now())[0]!, plan_sha256: 'sha256:plan-a', risk: 'write', ...over });
function optsFor(a: Action, over: Partial<ApproveOptions> = {}): ApproveOptions {
  const o = { challenge: challenge(), action_sha256: 'sha256:act', plan_sha256: a.plan_sha256 ?? null, expires_at: '2030-01-01T00:00:00Z', ...over };
  return { ...o, device_payload: signingPayload(o.challenge, a.id, o.action_sha256, o.plan_sha256), ...over };
}
const v1 = new Features([OP.approveOptions, OP.approverKeys], 'openapi');
const rec = (spki: string): ApprovalKeyRecord => ({ hubUrl: 'https://hub.example', keyId: 'ak_1', publicKey: spki, securityLevel: 'strongbox' });

describe('signing payload', () => {
  it('is the gateway payload: tag, action id, action hash, plan hash or "-", challenge (approver_keys.signing_payload)', () => {
    expect(signingPayload('c', 'act-1', 'sha256:a', 'sha256:p')).toBe('onemind-approve-v1\nact-1\nsha256:a\nsha256:p\nc');
    expect(signingPayload('c', 'act-1', 'sha256:a', null)).toBe('onemind-approve-v1\nact-1\nsha256:a\n-\nc');
  });

  it('accepts only a P-256 SubjectPublicKeyInfo and only a signature by that key over that payload', () => {
    const k = fakeKey();
    expect(pointFromSpki(k.spki)).toHaveLength(65);
    expect(() => pointFromSpki(toB64url(new Uint8Array(91)))).toThrow(/P-256/);
    expect(verifyDeviceSignature(k.spki, 'x', k.signDer('x'))).toBe(true);
    expect(verifyDeviceSignature(k.spki, 'y', k.signDer('x'))).toBe(false);
    expect(verifyDeviceSignature(fakeKey().spki, 'x', k.signDer('x'))).toBe(false);
  });
});

describe('approving with the approval key', () => {
  function setup(over: { native?: Partial<ApprovalKeyNative>; options?: (a: Action) => ApproveOptions; approve?: jest.Mock } = {}) {
    const k = fakeKey();
    Object.assign(k.native, over.native ?? {});
    const approve = over.approve ?? jest.fn(async () => ({ ...card(), state: 'accepted' as const }));
    const approveOptions = jest.fn(async () => (over.options ?? optsFor)(card()));
    const api = v0Api({ approveOptions, approve });
    const ctx = { features: v1, ownerHasPasskey: false, hubUrl: 'https://hub.example', approvalKey: makeSigner(rec(k.spki), k.native, new Set()) };
    return { k, api, approve, approveOptions, ctx };
  }

  it('signs the payload inside the biometric prompt, shows the plan, and sends a signature that verifies', async () => {
    const { k, api, approve, ctx } = setup();
    const r = await decide(api, card(), 'approve', ctx);
    expect(r).toMatchObject({ ok: true, message: "Approved with this phone's approval key: Install ollama (accepted)." });
    const [payload, title, subtitle] = k.native.sign.mock.calls[0]!;
    expect(title).toBe('Approve: Install ollama');
    expect(subtitle).toMatch(/^Plan plan-a · Reversible change$/);
    const body = approve.mock.calls[0]![1];
    expect(body).toMatchObject({ plan_sha256: 'sha256:plan-a', device_signature: { key_id: 'ak_1', challenge: expect.any(String) } });
    expect(body.webauthn).toBeUndefined();
    expect(verifyDeviceSignature(k.spki, payload, body.device_signature.signature)).toBe(true);
  });

  it('refuses a changed plan: the hub plan differs from the card, nothing is signed or sent', async () => {
    const { k, api, approve, ctx } = setup({ options: (a) => optsFor(a, { plan_sha256: 'sha256:plan-b' }) });
    const r = await decide(api, card(), 'approve', ctx);
    expect(r).toMatchObject({ ok: false, reason: 'plan_changed' });
    expect(k.native.sign).not.toHaveBeenCalled();
    expect(approve).not.toHaveBeenCalled();
  });

  it('refuses a payload for another plan than the card shows, even when plan_sha256 matches', async () => {
    const a = card();
    const forged = (x: Action) => {
      const o = optsFor(x);
      return { ...o, device_payload: signingPayload(o.challenge, x.id, o.action_sha256, 'sha256:plan-b') };
    };
    const { k, api, approve, ctx } = setup({ options: forged });
    const r = await decide(api, a, 'approve', ctx);
    expect(r).toMatchObject({ ok: false, code: 'approval_key', reason: 'payload_mismatch' });
    expect(k.native.sign).not.toHaveBeenCalled();
    expect(approve).not.toHaveBeenCalled();
  });

  it('refuses a replayed signature: an old signature for a new challenge never reaches the hub', async () => {
    const { k, api, approve, ctx } = setup();
    expect(await decide(api, card(), 'approve', ctx)).toMatchObject({ ok: true });
    const old = approve.mock.calls[0]![1].device_signature.signature as string;
    k.native.sign.mockImplementationOnce(async () => old);
    const r = await decide(api, card(), 'approve', ctx);
    expect(r).toMatchObject({ ok: false, reason: 'bad_signature' });
    expect(approve).toHaveBeenCalledTimes(1);
  });

  it('refuses a replayed challenge: the same challenge is never signed twice', async () => {
    const fixed = optsFor(card());
    const { k, api, approve, ctx } = setup({ options: () => fixed });
    expect(await decide(api, card(), 'approve', ctx)).toMatchObject({ ok: true });
    expect(await decide(api, card(), 'approve', ctx)).toMatchObject({ ok: false, reason: 'replay' });
    expect(k.native.sign).toHaveBeenCalledTimes(1);
    expect(approve).toHaveBeenCalledTimes(1);
  });

  it.each([[true], [''], [{ ok: true }], [undefined]])('refuses a bare success flag (%p) from the native side', async (flag) => {
    const { api, approve, ctx } = setup({ native: { sign: jest.fn(async () => flag as unknown as string) } });
    const r = await decide(api, card(), 'approve', ctx);
    expect(r).toMatchObject({ ok: false, code: 'approval_key', reason: 'bad_signature' });
    expect(approve).not.toHaveBeenCalled();
  });

  it('a new enrolment (key invalidated) is refused and says how to set the key up again', async () => {
    const err = Object.assign(new Error('a new fingerprint or face was added'), { code: 'ERR_KEY_INVALIDATED' });
    const { api, approve, ctx } = setup({ native: { sign: jest.fn(async () => Promise.reject(err)) } });
    const r = await decide(api, card(), 'approve', ctx);
    expect(r).toMatchObject({ ok: false, reason: 'invalidated' });
    expect(r.message).toMatch(/Set up the approval key again/);
    expect(approve).not.toHaveBeenCalled();
  });

  it('when the hub refuses a device key for this risk (F-2), it falls back to the passkey', async () => {
    const assertion = { id: 'c', clientDataJSON: 'd', authenticatorData: 'e', signature: 'f' };
    const passkeys: Passkeys = { supported: () => true, get: jest.fn(async () => assertion), create: jest.fn() };
    const approve = jest
      .fn()
      .mockRejectedValueOnce(new ApiError(401, 'unauthenticated', 'approve this with your passkey', { reason: 'step_up_required' }))
      .mockResolvedValueOnce({ ...card(), state: 'accepted', approval: 'passkey' });
    const { api, ctx } = setup({ approve });
    const r = await decide(api, card({ risk: 'destructive' }), 'approve', { ...ctx, passkeys });
    expect(r).toMatchObject({ ok: true, message: expect.stringMatching(/with your passkey/) });
    expect(approve.mock.calls[0][1].device_signature).toBeDefined();
    expect(approve.mock.calls[1][1]).toMatchObject({ webauthn: assertion });
    expect(approve.mock.calls[1][1].device_signature).toBeUndefined();
  });

  it('a hub without device signing (no device_payload) gets a plain approval, not a surprise passkey prompt', async () => {
    const plain = (a: Action) => {
      const o: Partial<ApproveOptions> = optsFor(a);
      delete o.device_payload;
      return o as ApproveOptions;
    };
    const passkeys: Passkeys = { supported: () => true, get: jest.fn(), create: jest.fn() };
    const { k, api, approve, ctx } = setup({ options: plain });
    const r = await decide(api, card(), 'approve', { ...ctx, passkeys });
    expect(r).toMatchObject({ ok: true });
    expect(k.native.sign).not.toHaveBeenCalled();
    expect(passkeys.get).not.toHaveBeenCalled();
    expect(approve.mock.calls[0]![1]).toEqual({ plan_sha256: 'sha256:plan-a' });
  });

  it('the live client sends device_signature in the approve body', async () => {
    const fetchFn = jest.fn(async () => new Response(JSON.stringify(card()), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    const sig = { key_id: 'ak_1', challenge: 'c', signature: 's' };
    await new HttpApi({ token: 't', baseUrl: 'https://h', fetchFn }).approve('a', { device_signature: sig });
    const init = (fetchFn.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(init.body as string)).toEqual({ device_signature: sig });
  });
});

describe('enrolment', () => {
  it('registers the public key as hardware-reported and remembers it for this hub only', async () => {
    const k = fakeKey();
    const approverKeyRegister = jest.fn(async () => ({ key_id: 'ak_9', label: 'Android phone', key_kind: 'hardware-reported', fingerprint: 'sha256:x', created_at: '', last_used_at: null, revoked_at: null }));
    const api = v0Api({ approverKeyRegister });
    const r = await enrol(api, 'https://hub.example', 'Android phone', k.native);
    expect(approverKeyRegister).toHaveBeenCalledWith({ public_key: k.spki, label: 'Android phone', key_kind: 'hardware-reported' });
    expect(r).toMatchObject({ keyId: 'ak_9', securityLevel: 'strongbox' });
    expect(await loadRecord('https://hub.example')).toEqual(r);
    expect(await loadRecord('https://other.example')).toBeNull();

    const approverKeyRevoke = jest.fn(async () => undefined);
    await forget(v0Api({ approverKeyRevoke }), r, k.native);
    expect(approverKeyRevoke).toHaveBeenCalledWith('ak_9');
    expect(k.native.remove).toHaveBeenCalled();
    expect(await loadRecord('https://hub.example')).toBeNull();
  });

  it('a software key is reported as software, and a hub refusal deletes the new key', async () => {
    const k = fakeKey();
    k.native.create.mockResolvedValueOnce({ publicKey: k.spki, securityLevel: 'software' as never });
    const approverKeyRegister = jest.fn(async () => {
      throw new ApiError(401, 'unauthenticated', 'sign in again with your passkey', { reason: 'step_up_required' });
    });
    await expect(enrol(v0Api({ approverKeyRegister }), 'https://hub.example', 'p', k.native)).rejects.toMatchObject({ reason: 'step_up_required' });
    expect((approverKeyRegister.mock.calls[0] as unknown as [{ key_kind: string }])[0].key_kind).toBe('software');
    expect(k.native.remove).toHaveBeenCalled();
  });

  it('without the native module (iPhone for now, Expo Go) there is no enrolment', async () => {
    await expect(enrol(v0Api({ approverKeyRegister: jest.fn() }), 'https://hub.example', 'p', undefined)).rejects.toMatchObject({ kind: 'not_on_phone' });
  });
});
