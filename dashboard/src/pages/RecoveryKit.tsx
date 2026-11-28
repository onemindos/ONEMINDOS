// SPDX-License-Identifier: Apache-2.0
import { useState, type FormEvent } from 'react';
import { Button } from '@onemind/ui';
import type { components } from '@onemind/sdk';
import { t } from '../i18n';

type Kit = components['schemas']['SetupKit'];
type Method = components['schemas']['SetupFinishBody']['method'];

export function RecoveryKit({ kit, busy, onSaved }: { kit: Kit; busy: boolean; onSaved: (method: Method) => void }) {
  const [method, setMethod] = useState<Method>();
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState(false);
  const save = (how: Method) => {
    try {
      if (how === 'download') {
        const text = [t('kit.title'), t('kit.warning'), '', t('kit.code'), kit.recovery_code,
          ...(kit.disk_recovery_key ? ['', t('kit.diskKey'), kit.disk_recovery_key] : [])].join('\n');
        const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
        const link = document.createElement('a');
        link.href = url;
        link.download = 'onemind-recovery-kit.txt';
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(URL.revokeObjectURL.bind(URL, url), 1000);
      } else {
        // This sheet also works from the password reset screen. Print CSS leaves only the kit visible.
        window.print();
      }
      setMethod(how);
      setConfirmed(false);
      setError(false);
    } catch {
      setError(true);
    }
  };
  const finish = (event: FormEvent) => {
    event.preventDefault();
    if (method && confirmed && !busy) onSaved(method);
  };
  return (
    <form onSubmit={finish} className="dash-signin-form">
      <div className="dash-kit-sheet">
        <h2>{t('kit.title')}</h2>
        <p className="om-note om-tone-warn">{t('kit.warning')}</p>
        <dl>
          <dt>{t('kit.code')}</dt><dd><code>{kit.recovery_code}</code></dd>
          {kit.disk_recovery_key && <><dt>{t('kit.diskKey')}</dt><dd><code>{kit.disk_recovery_key}</code></dd></>}
        </dl>
      </div>
      <div className="dash-identity-actions">
        <Button type="button" onClick={() => save('download')} disabled={busy}>{t('kit.download')}</Button>
        <Button type="button" onClick={() => save('print')} disabled={busy}>{t('kit.print')}</Button>
      </div>
      {error && <p role="alert">{t('kit.saveFailed')}</p>}
      <label className="dash-identity-check">
        <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} disabled={!method || busy} />
        {t('kit.saved')}
      </label>
      <Button type="submit" variant="primary" disabled={!method || !confirmed || busy}>{t('kit.finish')}</Button>
    </form>
  );
}
