// SPDX-License-Identifier: Apache-2.0
import { useId, useMemo, useState, type FormEvent } from 'react';
import { OneMind, OneMindError, type paths } from '@onemind/sdk';
import { Button, Card } from '@onemind/ui';
import { t } from '../i18n';
import { useSignedIn } from '../session';

type Export = paths['/v1/config/export']['get']['responses'][200]['content']['application/json'];
type Diff = paths['/v1/config/diff']['post']['responses'][200]['content']['application/json'];
type DiffBody = paths['/v1/config/diff']['post']['requestBody']['content']['application/json'];

function saveYaml(name: string, yaml: string) {
  const url = URL.createObjectURL(new Blob([yaml], { type: 'application/yaml' }));
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    link.click();
  } finally {
    URL.revokeObjectURL(url);
  }
}

function readYaml(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
}

export function SettingsConfig() {
  const { mock, canDecide, token } = useSignedIn();
  if (mock || canDecide === 'no') return null;
  return <LiveConfig key={token} token={token} />;
}

function LiveConfig({ token }: { token: string }) {
  const api = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const input = useId();
  const [files, setFiles] = useState<File[]>([]);
  const [exported, setExported] = useState<Export>();
  const [diff, setDiff] = useState<Diff>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<'export' | 'compare'>();

  async function exportConfig() {
    setBusy('export');
    setExported(undefined);
    setError('');
    try {
      const result = await api.call<Export>({ method: 'GET', path: '/v1/config/export' });
      if (!Object.keys(result?.files ?? {}).length) {
        setError(t('config.exportFailed'));
        return;
      }
      setExported(result);
    } catch (error) {
      setError(error instanceof OneMindError && error.status === 403 ? t('config.ownerOnly') : t('config.exportFailed'));
    } finally {
      setBusy(undefined);
    }
  }

  async function compare(event: FormEvent) {
    event.preventDefault();
    if (!files.length || busy) return;
    setBusy('compare');
    setDiff(undefined);
    setError('');
    try {
      const entries = await Promise.all(files.map(async (file) => [file.name, await readYaml(file)] as const));
      const body: DiffBody = { files: Object.fromEntries(entries) };
      setDiff(await api.call<Diff>({ method: 'POST', path: '/v1/config/diff', body }));
    } catch (error) {
      if (error instanceof OneMindError && error.status === 403) setError(t('config.ownerOnly'));
      else if (error instanceof OneMindError && error.status === 422) setError(error.message);
      else setError(t('config.compareFailed'));
    } finally {
      setBusy(undefined);
    }
  }

  return <Card title={t('config.title')}>
    <p>{t('config.privateGit')}</p>
    <Button busy={busy === 'export'} disabled={Boolean(busy)} onClick={() => void exportConfig()}>{t('config.export')}</Button>
    <div aria-live="polite">
      {exported && <ul>
        {Object.entries(exported.files).map(([name, yaml]) => <li key={name}>
          <Button variant="secondary" onClick={() => saveYaml(name, yaml)}>{t('config.download', { name })}</Button>
        </li>)}
      </ul>}
    </div>

    <form className="dash-stack" onSubmit={(event) => void compare(event)}>
      <label htmlFor={input}>{t('config.files')}</label>
      <input id={input} type="file" accept=".yaml" multiple disabled={Boolean(busy)} onChange={(event) => {
        setFiles(Array.from(event.currentTarget.files ?? []));
        setDiff(undefined);
        setError('');
      }} />
      <div><Button type="submit" busy={busy === 'compare'} disabled={!files.length || Boolean(busy)}>{t('config.compare')}</Button></div>
    </form>
    {error && <p className="om-note om-tone-bad" role="alert">{error}</p>}
    {diff && <>
      <p role="status">{diff.changes.length ? t('config.changed') : t('config.unchanged')}</p>
      {diff.blockers.length > 0 && <div className="om-note om-tone-warn">
        <h3>{t('config.blockers')}</h3>
        <ul>{diff.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
      </div>}
      {diff.changes.map((change) => <details key={change.file} open>
        <summary>{change.file}</summary>
        <div className="dash-config-diff">
          <div><h3>{t('config.live')}</h3><pre>{change.before}</pre></div>
          <div><h3>{t('config.proposed')}</h3><pre>{change.after}</pre></div>
        </div>
      </details>)}
    </>}
  </Card>;
}
