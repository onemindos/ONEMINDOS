// SPDX-License-Identifier: Apache-2.0
import type { components } from '@onemind/sdk';
import type { CatalogApp, Plan } from '../api/types';
import { useHubData } from '../data';
import { sdkOf } from '../api/client';
import { useLoad } from '../lib/useLoad';
import { useSignedIn } from '../session';
import { Card, H2, Row } from '../ui/bits';

type CatalogDetails = components['schemas']['CatalogApp'];
type Placement = components['schemas']['AppPlacement'];

export function useAppPageDetails(id: string) {
  const { api, features } = useSignedIn();
  const sdk = sdkOf(api);
  const hasDetail = features.has('GET /v1/apps/{}');
  const hasPlacement = features.has('GET /v1/apps/{}/placement');
  const { data } = useLoad(async () => {
    const path = `/v1/apps/${encodeURIComponent(id)}`;
    const [details, placement] = await Promise.all([
      sdk && hasDetail ? sdk.call<CatalogDetails>({ method: 'GET', path }).catch(() => undefined) : undefined,
      sdk && hasPlacement ? sdk.call<Placement>({ method: 'GET', path: `${path}/placement` }).catch(() => undefined) : undefined,
    ]);
    return { id, details, placement };
  }, [sdk, id, hasDetail, hasPlacement]);
  return data?.id === id ? data : undefined;
}

export function AppFacts({ app, placement }: { app: CatalogApp; placement?: Placement }) {
  const { nodes } = useHubData();
  const selected = placement?.node_id;
  const runsOn = selected ? nodes?.find((n) => n.node_id === selected)?.hostname ?? selected : undefined;
  if (!app.version && !runsOn && !app.archs?.length) return null;
  return (
    <Card testID="app-facts">
      {app.version && <Row label="Version" value={app.version} />}
      {runsOn && <Row label={app.installed ? 'Placement' : 'Runs on'} value={runsOn} />}
      {!runsOn && !!app.archs?.length && <Row label="Supported architectures" value={app.archs.join(', ')} />}
    </Card>
  );
}

/** These are reported plan effects. An absent effect is never presented as a permission guarantee. */
export function AppTrust({ app, details, plan }: { app: CatalogApp; details?: CatalogDetails; plan?: Plan | null }) {
  const scan = details?.scan ?? app.scan;
  const licence = details?.license ?? app.license;
  const scannedAt = scan?.scanned_at ? new Date(scan.scanned_at) : undefined;
  const scanTime = scannedAt && Number.isFinite(scannedAt.getTime()) ? scannedAt.toLocaleString() : undefined;
  const findings = scan && 'reason' in scan && typeof scan.reason === 'string' ? scan.reason : undefined;
  const volumes = (plan?.volumes ?? []).flatMap((v) =>
    v && typeof v === 'object' && 'mount_path' in v && typeof v.mount_path === 'string' ? [v.mount_path] : [],
  );
  const paths = plan && 'network_paths' in plan && Array.isArray(plan.network_paths) ? plan.network_paths.flatMap((p: unknown) => {
    if (!p || typeof p !== 'object' || !('from' in p) || typeof p.from !== 'string' ||
        !('to' in p) || typeof p.to !== 'string' || !('port' in p) || typeof p.port !== 'number') return [];
    return [`${p.from} → ${p.to}, TCP ${p.port}`];
  }) : [];
  return (
    <>
      {(licence || scan) && <Card testID="app-trust">
        <H2>Trust</H2>
        {licence && <Row label="Licence" value={licence} />}
        {scan && scanTime && <Row label="Security scan" value={`${scan.result === 'pass' ? 'Passed' : 'Failed'} · ${scanTime}`} />}
        {findings && <Row label="Scan findings" value={findings} />}
      </Card>}
      {(volumes.length > 0 || paths.length > 0 || app.web_port != null) && <Card testID="app-access">
        <H2>What it can touch</H2>
        {volumes.length > 0 && <Row label="Folders" value={volumes.join(', ')} />}
        {paths.length > 0 && <Row label="Network paths in this plan" value={paths.join('\n')} />}
        {app.web_port != null && <Row label="Declared web port" value={app.web_port} />}
      </Card>}
    </>
  );
}
