// SPDX-License-Identifier: Apache-2.0
// @onemind/ui public API. Import the styles once: `import '@onemind/ui/ui.css'`.
import './styles/index.css';
import { toJson } from './tokens/tokens';

export { palette, light, dark, scale, shadow, TONES, toCss } from './tokens/tokens';
export type { Tone, Theme, ColorRole } from './tokens/tokens';
/** Token values as JSON text (written to dist/tokens.json for the mobile app). */
export const tokensJson = toJson;

export { AppShell, PageHeader } from './components/AppShell';
export type { AppShellProps, NavItem } from './components/AppShell';
export { ApprovalCard, ACTION_STATE, actionTitle, equivalentCall, requesterPill } from './components/ApprovalCard';
export type { ActionSummary, ActionState, ApprovalCardProps } from './components/ApprovalCard';
export { Button } from './components/Button';
export type { ButtonProps, ButtonVariant } from './components/Button';
export { Card } from './components/Card';
export type { CardProps } from './components/Card';
export { Dialog } from './components/Dialog';
export type { DialogProps } from './components/Dialog';
export { EmptyState } from './components/EmptyState';
export type { EmptyStateProps } from './components/EmptyState';
export { Icon, ICON_NAMES } from './components/Icon';
export type { IconName, IconProps } from './components/Icon';
export { Meter } from './components/Meter';
export type { MeterProps } from './components/Meter';
export { NodeCard } from './components/NodeCard';
export type { NodeSummary } from './components/NodeCard';
export { StatusPill, FreshnessPill } from './components/StatusPill';
export type { StatusPillProps } from './components/StatusPill';
export { Table } from './components/Table';
export type { Column, TableProps } from './components/Table';
export { ThemeSwitch } from './components/ThemeSwitch';
export { ToastProvider, useToast, TOAST_MS } from './components/Toast';
export type { ToastInput } from './components/Toast';
export { TrustCard } from './components/TrustCard';
export type { AppTrust, Placement } from './components/TrustCard';

export { formatAgo, formatDay, formatIn, secondsSince } from './lib/time';
export { freshness, NODE_LIMITS, FRESHNESS_LABEL, FRESHNESS_TONE } from './lib/freshness';
export type { Freshness, FreshnessLimits } from './lib/freshness';
export { installBlockReason, safeHttpUrl, SCAN_MAX_AGE_MS } from './lib/trust';
export type { AppTier, ScanSummary, CosignState } from './lib/trust';
export { applyTheme, storedTheme } from './lib/theme';
export type { ThemeChoice } from './lib/theme';
export * from './customize';
export * from './home';
export * from './backups';
export * from './settings';
export * from './store';
export * from './shell';
