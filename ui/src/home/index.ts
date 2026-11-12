// SPDX-License-Identifier: Apache-2.0
// Home launcher (docs/design/IA.md §2.1; parity PU-04). Styles in home.css; tokens in homeTokens.ts.
// Names are Home-specific so they never clash with the other ui/ areas' exports.
export { HomeScreen, HUB_LIMITS, WEATHER_STALE_S } from './HomeScreen';
export type { HomeScreenProps, HomeWallpaper } from './HomeScreen';
export { WidgetFrame } from './WidgetFrame';
export type { WidgetFrameProps, WidgetBodyState } from './WidgetFrame';
export { WidgetGrid } from './WidgetGrid';
export { WidgetGallery, galleryOptions as widgetGalleryOptions } from './WidgetGallery';
export { AppGrid as HomeAppGrid, filterApps as filterHomeApps } from './AppGrid';
export { Dock as HomeDock } from './Dock';
export { renderWidget, widgetName, DEFAULT_LINKS as HOME_DEFAULT_LINKS } from './widgets';
export type { HomeLinks, WidgetContext } from './widgets';
export {
  DEFAULT_LAYOUT as DEFAULT_HOME_LAYOUT,
  MAX_WIDGETS,
  MAX_PINNED,
  addWidget,
  browserLayoutStore as browserHomeLayoutStore,
  dockApps,
  moveWidget,
  movePin,
  removeWidget,
  resizeWidget,
  sanitizeLayout as sanitizeHomeLayout,
  togglePin,
} from './layout';
export type { HomeLayout, LayoutStore as HomeLayoutStore, WidgetInstance, WidgetKind, WidgetSize } from './layout';
export { greeting as homeGreeting, summaryLine as homeSummaryLine, formatUptime } from './greeting';
export { HOME_WALLPAPER_IDS, homeWallpapers } from './homeTokens';
export type { HomeWallpaperId } from './homeTokens';
export type {
  HomeData,
  HomeNode,
  HomeApp,
  AppRunState,
  AppWidgetDecl,
  AppWidgetPayload,
  ActivityItem,
  BackupStatus,
  UpdatesStatus,
  MeshStatus,
  WeatherSlot,
  Loadable as HomeLoadable,
} from './types';
