// SPDX-License-Identifier: Apache-2.0
// "Trust this box": step 0 of signing in. The box signs its own certificate, and browsers refuse
// passkeys on a page with a certificate error, so a new device must trust the box CA first. Both
// links are open gateway routes (public data, no secret), so they work before anyone is signed in.
import { t } from '../i18n';

export const CA_URL = '/v1/tls/ca.crt';
export const PROFILE_URL = '/v1/tls/onemind.mobileconfig';

export function TrustThisBox() {
  return (
    <details className="dash-trust">
      <summary>{t('trust.title')}</summary>
      <p className="om-hint">{t('trust.why')}</p>
      <p className="dash-signin-links">
        <a className="om-link" href={PROFILE_URL} download>
          {t('trust.profile')}
        </a>
        <a className="om-link" href={CA_URL} download>
          {t('trust.ca')}
        </a>
      </p>
      <ul className="om-hint dash-trust-steps">
        <li>{t('trust.apple')}</li>
        <li>{t('trust.mac')}</li>
        <li>{t('trust.android')}</li>
        <li>{t('trust.firefox')}</li>
      </ul>
    </details>
  );
}
