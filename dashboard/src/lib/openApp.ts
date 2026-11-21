// SPDX-License-Identifier: Apache-2.0
// "Open" for an installed app (UMB-P02, #139). The app lives at its own name behind the OneMind
// sign-in, so before the new tab loads the gateway gives this browser the app-host cookie.
import type { OneMindApi } from '../api/client';

/**
 * The tab opens first, inside the click, because browsers block a window opened after an await.
 * It goes to the app only once the sign-in cookie is set; if that fails the tab is closed and
 * the error is thrown, so a person never lands on a bare 401 page without knowing why.
 */
export async function openApp(api: Pick<OneMindApi, 'openAppSession'>, url: string, win: Pick<Window, 'open'> = window): Promise<void> {
  const tab = win.open('about:blank', '_blank');
  if (tab) tab.opener = null;
  try {
    await api.openAppSession?.();
  } catch (e) {
    tab?.close();
    throw e;
  }
  if (tab) tab.location.href = url;
  else win.open(url, '_blank', 'noopener');
}

/** Click handler wrapper: a failed sign-in is said out loud, not swallowed. */
export function openAppOrSay(api: Pick<OneMindApi, 'openAppSession'>, name: string, url: string): void {
  openApp(api, url).catch((e: unknown) => {
    window.alert(`OneMind could not open ${name}: ${e instanceof Error ? e.message : 'sign-in failed'}`);
  });
}
