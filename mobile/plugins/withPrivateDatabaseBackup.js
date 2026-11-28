// SPDX-License-Identifier: Apache-2.0
const { mkdir, writeFile } = require('node:fs/promises');
const path = require('node:path');
const { AndroidConfig, withAndroidManifest, withDangerousMod } = require('expo/config-plugins');

// Keep Expo SecureStore's shared preference allowlist. Explicitly exclude the database
// folder even though the allowlist already excludes the whole file domain.
const rules = `    <include domain="sharedpref" path="."/>
    <exclude domain="sharedpref" path="SecureStore"/>
    <exclude domain="file" path="onemind-app-databases/" tools:ignore="FullBackupContent"/>`;

module.exports = function withPrivateDatabaseBackup(config) {
  config = withAndroidManifest(config, mod => {
    const app = AndroidConfig.Manifest.getMainApplicationOrThrow(mod.modResults);
    app.$['android:fullBackupContent'] = '@xml/onemind_backup_rules';
    app.$['android:dataExtractionRules'] = '@xml/onemind_data_extraction_rules';
    return mod;
  });
  return withDangerousMod(config, ['android', async mod => {
    const xml = path.join(mod.modRequest.platformProjectRoot, 'app/src/main/res/xml');
    await mkdir(xml, { recursive: true });
    await writeFile(path.join(xml, 'onemind_backup_rules.xml'), `<full-backup-content xmlns:tools="http://schemas.android.com/tools">
${rules}
</full-backup-content>
`);
    await writeFile(path.join(xml, 'onemind_data_extraction_rules.xml'), `<data-extraction-rules xmlns:tools="http://schemas.android.com/tools">
  <cloud-backup>
${rules}
  </cloud-backup>
  <device-transfer>
${rules}
  </device-transfer>
</data-extraction-rules>
`);
    return mod;
  }]);
};
