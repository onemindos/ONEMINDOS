// SPDX-License-Identifier: Apache-2.0
// Choose what to back up: the whole library, or some albums.
import { useEffect } from 'react';
import { Switch, Text, View } from 'react-native';
import { Card, Loading, P, Screen, s } from '../ui/bits';
import { useTheme } from '../ui/theme';
import { usePhotoBackup } from './context';

export function PhotoAlbumsScreen() {
  const t = useTheme();
  const { albums, loadAlbums, settings, updateSettings } = usePhotoBackup();
  useEffect(() => {
    void loadAlbums();
  }, [loadAlbums]);
  const all = settings.albums === 'all';
  const chosen = new Set(all ? [] : settings.albums);

  const toggle = (id: string, on: boolean) => {
    const next = new Set(chosen);
    if (on) next.add(id);
    else next.delete(id);
    void updateSettings({ albums: [...next] });
  };

  return (
    <Screen testID="photo-albums">
      <Card>
        <View style={[s.row, { alignItems: 'center' }]}>
          <View style={{ flexShrink: 1 }}>
            <Text style={{ color: t.text, fontSize: 16, fontWeight: '600' }}>All photos and videos</Text>
            <P muted small>
              Everything in the library, including items added later.
            </P>
          </View>
          <Switch accessibilityLabel="All photos and videos" value={all} onValueChange={(on) => void updateSettings({ albums: on ? 'all' : [] })} testID="albums-all" />
        </View>
      </Card>
      {!all && chosen.size === 0 ? <P muted small>Pick at least one album, or nothing is backed up.</P> : null}
      {albums === undefined ? (
        <Loading what="albums" />
      ) : (
        <Card>
          {albums.map((a) => (
            <View key={a.id} style={[s.row, { alignItems: 'center', opacity: all ? 0.5 : 1 }]}>
              <View style={{ flexShrink: 1 }}>
                <Text style={{ color: t.text, fontSize: 15 }}>{a.title}</Text>
                <P muted small>
                  {a.count} item{a.count === 1 ? '' : 's'}
                </P>
              </View>
              <Switch accessibilityLabel={a.title} value={all || chosen.has(a.id)} disabled={all} onValueChange={(on) => toggle(a.id, on)} testID={`album-${a.id}`} />
            </View>
          ))}
          <P muted small>An item in several chosen albums is sent once.</P>
        </Card>
      )}
    </Screen>
  );
}
