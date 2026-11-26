// SPDX-License-Identifier: Apache-2.0
// Settings > Agents: the agent stop switch first, then the agent browser, the API tokens and agents list.
import { AgentBrowser } from './AgentBrowser';
import { AgentStop } from './AgentStop';
import { Tokens } from './Tokens';

export function AgentsSettings() {
  return (
    <>
      <AgentStop />
      <AgentBrowser />
      <Tokens />
    </>
  );
}
