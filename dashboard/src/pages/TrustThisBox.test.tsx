// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { TrustThisBox } from './TrustThisBox';

it('offers the box CA and the Apple profile from open gateway routes, with steps per platform', () => {
  render(<TrustThisBox />);
  expect(screen.getByRole('link', { name: /Download the box certificate/ })).toHaveAttribute('href', '/v1/tls/ca.crt');
  expect(screen.getByRole('link', { name: /Apple profile/ })).toHaveAttribute('href', '/v1/tls/onemind.mobileconfig');
  for (const os of [/iPhone or iPad/, /Mac:/, /Android/, /Firefox/]) expect(screen.getByText(os)).toBeInTheDocument();
});
