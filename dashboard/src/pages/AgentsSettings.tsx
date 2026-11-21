// SPDX-License-Identifier: Apache-2.0
// Settings > Agents: the agent stop switch first, then the API tokens and agents list.
import { AgentStop } from './AgentStop';
import { Tokens } from './Tokens';

export function AgentsSettings() {
  return (
    <>
      <AgentStop />
      <Tokens />
    </>
  );
}
