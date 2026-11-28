// SPDX-License-Identifier: Apache-2.0
// Settings > Agents: the agent stop switch first, then the API tokens and agents list.
import { AgentStop } from './AgentStop';
import { AgentInputs } from './AgentInputs';
import { FabricPolicy } from './FabricPolicy';
import { Tokens } from './Tokens';
import { useSignedIn } from '../session';

export function AgentsSettings() {
  const { mock, principal } = useSignedIn();
  return (
    <>
      <AgentStop />
      {!mock && principal?.role === 'owner' && <><FabricPolicy /><AgentInputs /></>}
      <Tokens />
    </>
  );
}
