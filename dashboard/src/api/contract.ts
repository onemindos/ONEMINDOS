// SPDX-License-Identifier: Apache-2.0
// CI-08 (#233): the dashboard's hand-written API types are checked against the generated
// @onemind/sdk schema at compile time. Rename or retype a field in core/ -> `make -C sdk gen`
// -> the SDK schema changes -> `npm run typecheck` fails right here, naming the field.
//
// Two rules per pair, applied to the keys the dashboard really reads:
//   1. every field the dashboard requires must still exist in the SDK schema;
//   2. what the gateway sends (SDK type) must fit what the dashboard expects, field by field.
// Fields the dashboard marks optional are ignored by rule 1 (it already tolerates their absence).
import type { components } from '@onemind/sdk';
import type { Action, CatalogApp, Instance, NodeRecord } from './types';

type Schemas = components['schemas'];

type RequiredKeys<T> = { [K in keyof T]-?: object extends Pick<T, K> ? never : K }[keyof T];

/** Keys the dashboard requires that the SDK schema no longer has. */
type Missing<Dash, Sdk> = Exclude<RequiredKeys<Dash>, keyof Sdk>;
/** string literal unions and open enums compare as plain `string`. */
type Widen<T> = T extends string ? string : T extends number ? number : T extends boolean ? boolean : T;
type IsScalar<T> = [NonNullable<T>] extends [string | number | boolean] ? true : false;
/**
 * Shared keys whose value is a scalar on the dashboard side and whose SDK type does not fit it.
 * Object-valued fields are skipped: the generated schema leaves many of them open (all-optional),
 * and the dashboard validates those at the boundary (see client.ts).
 */
type Mismatched<Dash, Sdk> = {
  [K in keyof Dash & keyof Sdk]-?: IsScalar<Dash[K]> extends true
    ? [Widen<NonNullable<Sdk[K]>>] extends [Widen<NonNullable<Dash[K]>>] ? never : K
    : never;
}[keyof Dash & keyof Sdk];

/** Resolves to `true`, or to a string literal type naming the drifted fields (a type error below). */
export type Agrees<Dash, Sdk> = [Missing<Dash, Sdk>] extends [never]
  ? [Mismatched<Dash, Sdk>] extends [never]
    ? true
    : { mismatched: Mismatched<Dash, Sdk> }
  : { missing: Missing<Dash, Sdk> };

export type Expect<T extends true> = T;

export type ContractChecks = [
  Expect<Agrees<Instance, Schemas['Instance']>>,
  Expect<Agrees<CatalogApp, Schemas['CatalogApp']>>,
  // The OpenAPI Node schema lists only the fields the gateway indexes; the rest of the heartbeat is
  // free-form there, so the check covers exactly those.
  Expect<Agrees<Pick<NodeRecord, 'node_id' | 'status' | 'last_seen' | 'hostname' | 'role' | 'board' | 'arch' | 'schema'>, Schemas['Node']>>,
  Expect<Agrees<Action, Schemas['Action']>>,
];
