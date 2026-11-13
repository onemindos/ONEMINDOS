// SPDX-License-Identifier: Apache-2.0
// Backups and Restore (contract §12.12): overview with verified-restore badges, destinations,
// Rewind browser, restore dialog and progress, emergency kit. See README.md.
export * from './types';
export {
  BADGE, HEALTH, RUN, REASON, KIND_LABEL, badgeView, destinationWhere, formatBytes, unitLabel, snapshotsByDay,
  breadcrumbs, volumeLabel, typeBackReady, normaliseAnswers, kitFileName, restoreConfirmed, restoreRequest, overviewNotice,
} from './logic';
export { BackupsOverview, BackupBadgePill } from './BackupsOverview';
export type { BackupsOverviewProps } from './BackupsOverview';
export { DestinationForm } from './DestinationForm';
export type { DestinationRequest } from './DestinationForm';
export { Rewind } from './Rewind';
export type { RewindProps } from './Rewind';
export { RestoreDialog, RestoreProgress } from './RestoreDialog';
export type { RestoreDialogProps } from './RestoreDialog';
export { EmergencyKit } from './EmergencyKit';
export type { EmergencyKitProps } from './EmergencyKit';
