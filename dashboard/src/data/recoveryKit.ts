// SPDX-License-Identifier: Apache-2.0
import type { OnboardingKit } from '@onemind/ui';
import type { FirstRunState, OneMindApi } from '../api/client';

export function recoveryKit(api: OneMindApi, state: FirstRunState['kit']): OnboardingKit | undefined {
  if (!api.issueKit || !api.confirmKit) return undefined;
  const { issueKit, confirmKit } = api;
  return {
    state: state.state, positions: state.positions, fingerprint: state.fingerprint ?? undefined,
    issue: async () => {
      const { kit, one_time } = await issueKit.call(api);
      const { groups, check, text, disk_recovery_key } = one_time;
      return {
        groups, check, text, positions: kit.positions, disk_key_kit: kit.disk_key_kit,
        ...(kit.fingerprint ? { fingerprint: kit.fingerprint } : {}),
        ...(disk_recovery_key ? { disk_recovery_key } : {}),
      };
    },
    confirm: (answers, fingerprint) => fingerprint ? confirmKit.call(api, answers, fingerprint) : confirmKit.call(api, answers),
  };
}
