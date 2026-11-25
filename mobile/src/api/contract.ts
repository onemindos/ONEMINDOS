// SPDX-License-Identifier: Apache-2.0
// CI-08 (#233): the phone's hand-written API types (types.ts) are checked against the generated
// @onemind/sdk schema at compile time, as dashboard/src/api/contract.ts does for the dashboard.
// Rename or retype a field in core/ -> `make -C sdk gen` -> the SDK schema changes -> `npm run typecheck`
// fails right here, naming the field.
//
// Two rules per pair, applied to the keys the phone really reads:
//   1. every field the phone requires must still exist in the SDK schema;
//   2. what the gateway sends (SDK type) must fit what the phone expects, field by field.
// Fields the phone marks optional are ignored by rule 1 (it already tolerates their absence).
import type { components } from '@onemind/sdk';
import type {
  Action,
  AppLinks,
  CatalogApp,
  FamilyProfile,
  FirstRunSettings,
  FirstRunSettingsBody,
  Instance,
  KillSwitch,
  NodeRecord,
  PlanPreview,
  PrincipalRef,
  ScanSummary,
} from './types';

type Schemas = components['schemas'];

type RequiredKeys<T> = { [K in keyof T]-?: object extends Pick<T, K> ? never : K }[keyof T];
/**
 * The keys a schema names. Several generated schemas are open (`& { [key: string]: unknown }`, from
 * additionalProperties); an index signature would make every key look present and every value `unknown`.
 */
type KnownKeys<T> = keyof { [K in keyof T as string extends K ? never : number extends K ? never : K]: T[K] };

/** Keys the phone requires that the SDK schema no longer has. */
type Missing<Phone, Sdk> = Exclude<RequiredKeys<Phone>, KnownKeys<Sdk>>;
/** String literal unions and open enums compare as plain `string`. */
type Widen<T> = T extends string ? string : T extends number ? number : T extends boolean ? boolean : T;
type IsScalar<T> = [NonNullable<T>] extends [string | number | boolean] ? true : false;
/**
 * Shared keys whose value is a scalar on the phone's side and whose SDK type does not fit it.
 * Object-valued fields are skipped: the generated schema leaves many of them open (all-optional),
 * and the phone checks the shape of every answer at the boundary (client.ts `req`).
 */
type Mismatched<Phone, Sdk> = {
  [K in keyof Phone & KnownKeys<Sdk>]-?: IsScalar<Phone[K]> extends true
    ? [Widen<NonNullable<K extends keyof Sdk ? Sdk[K] : never>>] extends [Widen<NonNullable<Phone[K]>>] ? never : K
    : never;
}[keyof Phone & KnownKeys<Sdk>];

/** Resolves to `true`, or to an object type naming the drifted fields (a type error below). */
export type Agrees<Phone, Sdk> = [Missing<Phone, Sdk>] extends [never]
  ? [Mismatched<Phone, Sdk>] extends [never]
    ? true
    : { mismatched: Mismatched<Phone, Sdk> }
  : { missing: Missing<Phone, Sdk> };

export type Expect<T extends true> = T;

export type ContractChecks = [
  Expect<Agrees<Instance, Schemas['Instance']>>,
  Expect<Agrees<CatalogApp, Schemas['CatalogApp']>>,
  Expect<Agrees<AppLinks, Schemas['AppLinks']>>,
  Expect<Agrees<ScanSummary, Schemas['ScanSummary']>>,
  // The OpenAPI Node schema lists only the fields the gateway indexes; the rest of the heartbeat is
  // free-form there, so the check covers exactly those.
  Expect<Agrees<Pick<NodeRecord, 'node_id' | 'status' | 'last_seen' | 'hostname' | 'role' | 'board' | 'arch' | 'schema'>, Schemas['Node']>>,
  Expect<Agrees<Action, Schemas['Action']>>,
  Expect<Agrees<PrincipalRef, Schemas['PrincipalRef']>>,
  Expect<Agrees<PlanPreview, Schemas['PlanPreview']>>,
  Expect<Agrees<FamilyProfile, Schemas['FamilyProfile']>>,
  Expect<Agrees<KillSwitch, Schemas['KillSwitch']>>,
  // §12.41 first-run settings: what the phone reads back and what it sends.
  Expect<Agrees<FirstRunSettings, Schemas['OnboardingSettingsView']>>,
  Expect<Agrees<FirstRunSettingsBody, Schemas['OnboardingSettingsBody']>>,
];
