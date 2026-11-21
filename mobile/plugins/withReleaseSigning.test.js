// SPDX-License-Identifier: Apache-2.0
const { addReleaseSigning } = require('./withReleaseSigning');

describe('withReleaseSigning', () => {
  const out = addReleaseSigning('android {\n}\n');

  it('adds the block once', () => {
    expect(addReleaseSigning(out)).toBe(out);
  });
  it('takes versionCode from ONEMIND_VERSION_CODE, default 1', () => {
    expect(out).toMatch(/versionCode\(\(System.getenv\("ONEMIND_VERSION_CODE"\) \?: "1"\).toInteger\(\)\)/);
  });
  it('signs release only when a keystore path is given, and reads every secret from the environment', () => {
    expect(out).toMatch(/if \(System.getenv\("ANDROID_KEYSTORE_PATH"\)\)/);
    for (const v of ['ANDROID_KEYSTORE_PASSWORD', 'ANDROID_KEY_ALIAS', 'ANDROID_KEY_PASSWORD']) {
      expect(out).toContain(`System.getenv("${v}")`);
    }
    expect(out).not.toMatch(/storePassword\s+["']/);
  });
});
