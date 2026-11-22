// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { displayNameOf } from './homeMe';

describe('Home greeting name', () => {
  it('reads display_name from the principal, or from the top level when the gateway adds it there', () => {
    expect(displayNameOf({ principal: { kind: 'person', display_name: 'Zeus Delacruz' } })).toBe('Zeus');
    expect(displayNameOf({ display_name: 'ana', principal: { kind: 'person' } })).toBe('Ana');
  });

  it('gives no name when the field is absent, empty, a role word, or the caller is not a person', () => {
    expect(displayNameOf({ principal: { kind: 'person' } })).toBeUndefined();
    expect(displayNameOf({ principal: { kind: 'person', display_name: '  ' } })).toBeUndefined();
    expect(displayNameOf({ principal: { kind: 'person', display_name: 'Owner' } })).toBeUndefined();
    expect(displayNameOf({ principal: { kind: 'agent', display_name: 'Hermes' } })).toBeUndefined();
    expect(displayNameOf({ principal: { kind: 'person', display_name: 42 } })).toBeUndefined();
    expect(displayNameOf(null)).toBeUndefined();
  });
});
