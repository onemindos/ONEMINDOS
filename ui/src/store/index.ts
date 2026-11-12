// SPDX-License-Identifier: Apache-2.0
// App Store and installed-apps manager (docs/design/TAXONOMY.md, IA §2.2-2.3). See README.md.
// store.css is imported by bits.tsx: package.json marks .ts modules side-effect free, so a CSS
// import in this barrel would be dropped by the bundler.

export * from './types';
export { CATEGORIES, CATEGORY_BY_SLUG, DEPLOY_CLASSES, BROWSABLE_CLASSES, LICENCE_CLASSES, DEVICE_LABEL, EXPOSURE_LABEL, categoryLabel, isKnownTag } from './taxonomy';
export type { CategoryInfo, DeployClassInfo } from './taxonomy';
export {
  DEFAULT_FILTERS,
  filterApps,
  searchScore,
  tokenize,
  countByCategory,
  tagsInCategory,
  activeFilterCount,
  doesNotFit,
  primaryAction,
  buildRequest,
  apiEquivalent,
  cliEquivalent,
  isProposedAction,
  INSTALL_STEPS,
  JOB_LABEL,
  JOB_TONE,
  isJobActive,
  jobStepIndex,
  jobPercent,
  nextJobState,
  hasUpdate,
  formatMb,
} from './logic';
export type { MarketFilters, FilterResult, PrimaryAction } from './logic';
export { CategoryIcon } from './CategoryIcon';
export type { CategoryIconName } from './CategoryIcon';
export { AppTile, ClassPills, FitLine, LoadGate, StaleBanner, Skeleton, Tabs, RequestDetails } from './bits';
export type { TabDef } from './bits';
export { Market, AppCard } from './Market';
export type { MarketProps, MarketHandlers } from './Market';
export { AppDetail, StoreTrustCard, Requirements, Screenshots, ReleaseNotes } from './AppDetail';
export type { AppDetailProps } from './AppDetail';
export { InstallReview, reviewSteps, STEP_TITLE } from './InstallReview';
export type { InstallReviewProps, ReviewStep } from './InstallReview';
export { JobProgress, JobsTray } from './Jobs';
export { InstalledList, ManageApp, CredentialsCard, appStateView } from './Installed';
export type { InstalledListProps, ManageAppProps } from './Installed';
export { LogViewer, filterLogs } from './LogViewer';
export { TILE_HUES } from './storeTokens';
