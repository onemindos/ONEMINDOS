// SPDX-License-Identifier: Apache-2.0
export type PermissionState = 'Allowed' | 'Not asked' | 'Denied' | 'Blocked';

export function permissionState(response: { granted: boolean; canAskAgain: boolean; status?: string }): PermissionState {
  if (response.granted) return 'Allowed';
  if (response.status === 'undetermined') return 'Not asked';
  return response.canAskAgain ? 'Denied' : 'Blocked';
}
