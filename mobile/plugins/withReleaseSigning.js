// SPDX-License-Identifier: Apache-2.0
// Expo config plugin: release signing and versionCode for CI builds (no secrets in the repo).
// The generated android/app/build.gradle gets a block that reads, at build time:
//   ONEMIND_VERSION_CODE      integer, from the OS build number (the `-dev.N` of the image); default 1
//   ANDROID_KEYSTORE_PATH     path to the upload keystore (CI decodes ANDROID_KEYSTORE_BASE64 to it)
//   ANDROID_KEYSTORE_PASSWORD, ANDROID_KEY_ALIAS, ANDROID_KEY_PASSWORD
// With no keystore the release build keeps Expo's default (the debug key), so forks and today's repo still
// build; the CI script names such an APK "-dev-unsigned".
const { withAppBuildGradle } = require('expo/config-plugins');

const MARK = '// onemind: release signing + versionCode from the environment (plugins/withReleaseSigning.js)';

const BLOCK = `${MARK}
android {
    defaultConfig {
        versionCode((System.getenv("ONEMIND_VERSION_CODE") ?: "1").toInteger())
    }
    if (System.getenv("ANDROID_KEYSTORE_PATH")) {
        signingConfigs {
            upload {
                storeFile file(System.getenv("ANDROID_KEYSTORE_PATH"))
                storePassword System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias System.getenv("ANDROID_KEY_ALIAS")
                keyPassword System.getenv("ANDROID_KEY_PASSWORD")
            }
        }
        buildTypes {
            release {
                signingConfig signingConfigs.upload
            }
        }
    }
}
`;

function addReleaseSigning(gradle) {
  if (gradle.includes(MARK)) return gradle;
  return `${gradle.trimEnd()}\n\n${BLOCK}`;
}

const withReleaseSigning = (config) =>
  withAppBuildGradle(config, (c) => {
    c.modResults.contents = addReleaseSigning(c.modResults.contents);
    return c;
  });

module.exports = withReleaseSigning;
module.exports.addReleaseSigning = addReleaseSigning;
