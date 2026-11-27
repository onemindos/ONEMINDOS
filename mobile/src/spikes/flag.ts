// SPDX-License-Identifier: Apache-2.0
/**
 * Spike screens (docs/SPIKE-EDITOR.md) are reachable only in a dev build, or in a release build made with
 * EXPO_PUBLIC_ONEMIND_SPIKES=1 (inlined by Expo at build time). Nothing else links to them.
 */
export function spikesEnabled(
  env: string | undefined = process.env.EXPO_PUBLIC_ONEMIND_SPIKES,
  dev: boolean = __DEV__,
): boolean {
  return dev || env === '1';
}
