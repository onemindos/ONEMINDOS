// SPDX-License-Identifier: Apache-2.0
// Customization engine (parity gap PU-03): per-person appearance preferences, applied as token
// overrides. See ./README.md.
// customize.css is imported by preferences.ts (see the note there).

// Generic names are prefixed (APPEARANCE_*, Appearance*) so they never clash with other ui/ areas.
export {
  ACCENTS as APPEARANCE_ACCENTS,
  ACCENT_IDS as APPEARANCE_ACCENT_IDS,
  AA as WCAG_AA,
  deriveAccent,
  presetAccent,
  customAccent,
  accentWorstRatio,
  isAccentId as isAppearanceAccentId,
} from './accents';
export type {
  AccentId as AppearanceAccentId,
  AccentPreset as AppearanceAccentPreset,
  AccentSet as AppearanceAccentSet,
  DerivedAccent,
  ThemeName as AppearanceThemeName,
} from './accents';
export {
  contrast as contrastRatio,
  luminance as relativeLuminance,
  mix as mixHex,
  normalizeHex,
  hexToOklch,
  oklchToHex,
  withLightness,
} from './color';
export {
  WALLPAPERS as APPEARANCE_WALLPAPERS,
  WALLPAPER_IDS as APPEARANCE_WALLPAPER_IDS,
  minDim as wallpaperMinDim,
  paintedColors as wallpaperPaintedColors,
  wallpaperBackground,
  isWallpaperChoice,
  UNKNOWN_IMAGE_MIN_DIM,
} from './wallpapers';
export type { Wallpaper as AppearanceWallpaper, WallpaperId as AppearanceWallpaperId, WallpaperChoice, WallpaperKind } from './wallpapers';
export {
  DEFAULT_PREFERENCES as DEFAULT_APPEARANCE,
  FONT_SCALES as APPEARANCE_FONT_SCALES,
  MAX_BLUR as WALLPAPER_MAX_BLUR,
  STYLE_ID as APPEARANCE_STYLE_ID,
  normalizePreferences,
  scheduledTheme,
  msUntilNextSwitch,
  resolveThemeAttr,
  resolveAccent,
  accentSeed,
  effectiveDim,
  customizeCss,
  applyPreferences,
  clearPreferences,
} from './preferences';
export type {
  AppearancePreferences,
  ThemeMode as AppearanceThemeMode,
  AccentSource as AppearanceAccentSource,
  Density as AppearanceDensity,
  Corners as AppearanceCorners,
  MotionPref as AppearanceMotion,
  TransparencyPref as AppearanceTransparency,
  FontScale as AppearanceFontScale,
  ApplyEnv as AppearanceApplyEnv,
} from './preferences';
export {
  LocalPreferencesStore,
  ApiPreferencesStore,
  PendingStore as PendingPreferencesStore,
  PreferencesError,
  LOCAL_SLOT as APPEARANCE_STORAGE_SLOT,
  LOCAL_IMAGE_SLOT as APPEARANCE_IMAGE_STORAGE_SLOT,
  PREFERENCES_PATH,
  WALLPAPER_PATH,
  API_CONTRACT_STATUS,
} from './store';
export type { PreferencesStore, StoredPreferences, PreferencesErrorCode, ApiStoreOptions } from './store';
export { checkUpload as checkWallpaperUpload, sampleColors as sampleImageColors, prepareWallpaper, UPLOAD_MAX_BYTES as WALLPAPER_UPLOAD_MAX_BYTES, UPLOAD_TYPES as WALLPAPER_UPLOAD_TYPES } from './upload';
export { CustomizeProvider, useCustomize, useOptionalCustomize } from './CustomizeProvider';
export type { CustomizeProviderProps, CustomizeStatus, CustomizeContextValue, LoadPhase as AppearanceLoadPhase, PrefsSource as AppearanceSource } from './CustomizeProvider';
export { WallpaperLayer, WallpaperSurface, wallpaperLayers } from './WallpaperLayer';
export { ChoiceGroup as AppearanceChoiceGroup, RangeField as AppearanceRangeField, SettingRow as AppearanceSettingRow } from './controls';
export type { Choice as AppearanceChoice, ChoiceGroupProps as AppearanceChoiceGroupProps, RangeFieldProps as AppearanceRangeFieldProps } from './controls';
export { AppearanceSettings, AppearanceStatus, AppearancePreview, AppearanceApiEquivalent } from './AppearanceSettings';
