// SPDX-License-Identifier: Apache-2.0
const { addExclusion } = require('./withoutPlayServicesCredentials');

describe('withoutPlayServicesCredentials', () => {
  it('excludes the Play Services credentials bridge once', () => {
    const once = addExclusion('android {\n}\n');
    expect(once).toMatch(/exclude group: 'androidx.credentials', module: 'credentials-play-services-auth'/);
    expect(addExclusion(once)).toBe(once);
  });
});
