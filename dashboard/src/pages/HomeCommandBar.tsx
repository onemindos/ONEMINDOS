// SPDX-License-Identifier: Apache-2.0
import { Button } from '@onemind/ui';
import { openUrl } from '../data/adapters';
import type { CatalogApp } from '../api/types';

interface Props {
  apps: readonly Pick<CatalogApp, 'id' | 'installed' | 'web_port'>[];
  openPalette: () => void;
  location?: Pick<Location, 'hostname' | 'protocol'>;
}

/** The chat lives in the installed Hermes app behind the hub's app proxy. */
export function HomeCommandBar({ apps, openPalette, location }: Props) {
  const agent = apps.find((app) => app.id === 'hermes-agent');
  const url = agent && openUrl(agent, location);
  return (
    <div role="group" aria-label="Home commands" className="om-cz-swatches">
      <Button onClick={openPalette}>Run a command</Button>
      {url && <a className="om-btn om-btn-secondary" href={url} target="_blank" rel="noopener noreferrer">Ask an agent<span className="om-visually-hidden"> (opens Hermes in a new tab)</span></a>}
    </div>
  );
}
