// SPDX-License-Identifier: Apache-2.0
// Shell-wide pieces: command palette, notification centre, toasts, first-run wizard and the
// empty/loading/error/stale state system. See src/shell/README.md.
// Generic names are renamed on export so `export * from './shell'` never clashes with other areas.
// Styles are imported by each component too: this barrel is side-effect-free for bundlers.
import './shell.css';

export { CommandPalette, PaletteTrigger, usePaletteHotkey, hotkeyLabel as paletteHotkeyLabel } from './CommandPalette';
export type { CommandPaletteProps } from './CommandPalette';
export {
  buildCommands as buildPaletteCommands,
  searchCommands as searchPaletteCommands,
  scoreCommand as scorePaletteCommand,
  parseQuery as parsePaletteQuery,
  moveActive as movePaletteActive,
  isPaletteHotkey,
  pushRecent as pushRecentCommand,
  SETTINGS_COMMANDS as PALETTE_SETTINGS_COMMANDS,
  NAV_COMMANDS as PALETTE_NAV_COMMANDS,
  COMMAND_GROUPS as PALETTE_GROUPS,
} from './palette';
export type { PaletteCommand, PaletteApp, PaletteData, CommandGroup as PaletteGroup, ResultGroup as PaletteResultGroup } from './palette';

export { NotificationCentre, NotificationBell } from './NotificationCentre';
export type { NotificationCentreProps, NotificationBellProps } from './NotificationCentre';
export {
  KIND_META as NOTIFICATION_KINDS,
  NOTIFICATION_API,
  needsYou as notificationNeedsYou,
  unreadCount as unreadNotifications,
  filterNotifications,
  groupByDay as groupNotificationsByDay,
  setRead as setNotificationsRead,
  markAllRead as markAllNotificationsRead,
  safeDeepLink as safeNotificationLink,
} from './notifications';
export type { ShellNotification, NotificationKind, NotificationSeverity, NotificationFilter, DayGroup as NotificationDayGroup } from './notifications';

export { toastForNotification, toastForRequest, toastForRequestError, useNotificationToasts, newArrivals as newNotificationArrivals } from './toasts';
export type { Navigate as ShellNavigate } from './toasts';

export { Onboarding, AppGlyph as StarterAppGlyph } from './Onboarding';
export type { OnboardingProps } from './Onboarding';
export {
  ONBOARDING_STEPS,
  accentVars as accentStyleVars,
  emptyDraft as emptyOnboardingDraft,
  validateBoxName,
  slugifyBoxName,
  stepIssues as onboardingStepIssues,
  finishIssues as onboardingFinishIssues,
  furthestReachable as onboardingFurthestStep,
  finishRequests as onboardingRequests,
  initCommand as onemindInitCommand,
  offerable as offerableStarterApps,
  categoryCounts as starterCategoryCounts,
  toggleApp as toggleStarterApp,
  selectedMemoryMb as starterMemoryMb,
} from './firstRun';
export type { OnboardingDraft, StepId as OnboardingStepId, StarterApp, PasskeyState, BackupDestination } from './firstRun';

export { StateView, Skeleton as StateSkeleton } from './StateView';
export type { StateViewProps } from './StateView';
export { viewState, isSlow as isLoadingSlow, SLOW_AFTER_S, EMPTY_PRESETS, ERROR_COPY as GATEWAY_ERROR_COPY } from './states';
export type { ViewState, Resource as ShellResource, GatewayError as ShellGatewayError, GatewayErrorCode as ShellGatewayErrorCode, EmptyPreset, EmptyPresetId } from './states';

export { ShellIcon, SHELL_ICON_NAMES } from './icons';
export type { ShellIconName, ShellIconProps } from './icons';
