// SPDX-License-Identifier: Apache-2.0
// Settings, Activity (audit) and Approvals screens. Names are explicit (no `export *`) so they
// cannot collide with other areas of @onemind/ui; generic names carry a Settings prefix.
// Styles are imported by primitives.tsx, which every component here uses: package.json marks
// JS as side-effect free, so a CSS import in this barrel could be dropped by the bundler.

export { SettingsLayout, SETTINGS_SECTIONS } from './SettingsLayout';
export type { SettingsLayoutProps, SettingsSectionId, SettingsSectionMeta } from './SettingsLayout';
export { AccountSection, UsersSection, AgentsSection } from './SectionsAccess';
export type { SectionProps as SettingsSectionProps } from './SectionsAccess';
export { DevicesSection, NetworkSection, StorageSection, AboutSection } from './SectionsSystem';
export { BackupsSection, UpdatesSection, NotificationsSection, AutomationSection } from './SectionsCare';
export { AuditTimeline } from './AuditTimeline';
export type { AuditTimelineProps } from './AuditTimeline';
export { ApprovalsBoard, EffectsCard } from './ApprovalsBoard';
export type { ApprovalsBoardProps } from './ApprovalsBoard';
export { Async as SettingsAsync } from './primitives';
export { restoreBadge, chainBadge, tokenState, groupEffects, planRisk, inQuietHours, filterAudit, groupByDay, usageByCategory } from './logic';
export type {
  AboutData,
  AccountData,
  ActionPlan,
  ActivityData,
  AgentsData,
  ApiToken,
  AuditEntry,
  AuditVerify,
  AutomationRule,
  BackupsData,
  DevicesData,
  Effect as PlanEffect,
  GatewayError as SettingsGatewayError,
  Loadable as SettingsLoadable,
  NetworkData,
  NotificationsData,
  OnIntent as OnSettingsIntent,
  Person as SettingsPerson,
  SettingsIntent,
  StorageData,
  UpdatesData,
} from './types';
