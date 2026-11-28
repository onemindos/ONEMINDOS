// SPDX-License-Identifier: Apache-2.0
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { OneMind } from '@onemind/sdk';
import { sdkOf } from '../api/client';
import { useLoad } from '../lib/useLoad';
import type { RootParams } from '../nav';
import { useSignedIn } from '../session';
import { loadTips, tipsError, tipsScope } from '../tips/pack';
import { Button, Card, H1, Loading, P, Screen } from '../ui/bits';

type Props = NativeStackScreenProps<RootParams, 'Tips'>;

function PackScreen({ client, scope, route, navigation }: Props & { client: OneMind; scope: string }) {
  const resolved = useLoad(async () => {
    try {
      return { pack: await loadTips(client, scope) };
    } catch (error) {
      return { problem: tipsError(error) };
    }
  }, [client, scope]);
  const id = route.params?.id;
  const pack = resolved.data?.pack;
  const tip = pack?.tips.find(entry => entry.id === id);
  const allTips = () => navigation.setParams({ id: undefined });
  return <Screen testID="tips">
    <H1>{tip?.title ?? 'Tips'}</H1>
    {pack?.offline && <P muted>Offline · saved on this phone</P>}
    {resolved.loading && <Loading what="Tips" />}
    {resolved.data?.problem && <Card>
      <P>{resolved.data.problem}</P>
      <Button label="Retry" variant="secondary" onPress={() => void resolved.reload()} />
    </Card>}
    {pack && (id
      ? <>
        <P>{tip?.body ?? 'This tip is not available in your pack.'}</P>
        <Button label="All Tips" variant="secondary" onPress={allTips} />
      </>
      : pack.tips.length > 0
        ? pack.tips.map(entry => <Button key={entry.id} label={entry.title} variant="secondary" onPress={() => navigation.push('Tips', { id: entry.id })} />)
        : <P>No tips are available for this account.</P>)}
  </Screen>;
}

export function TipsScreen(props: Props) {
  const { api, connection } = useSignedIn();
  const client = sdkOf(api);
  const scope = tipsScope(connection.hubUrl, connection.token);
  return client
    ? <PackScreen key={scope} {...props} client={client} scope={scope} />
    : <Screen testID="tips"><H1>Tips</H1><P>Connect to a hub to read its Tips pack.</P></Screen>;
}
