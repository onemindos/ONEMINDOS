// SPDX-License-Identifier: Apache-2.0
// Settings > Notifications, SMS channel (#869): add one with a number, the provider's send URL, its
// token and a daily cap; the cap shows on the channel; a test shows the provider's receipt.
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/helpers';

const T = { timeout: 4000 };
const PHONE = '+1555' + '0100123'; // the +1 555 01xx range is kept for fiction

describe('SMS channel', () => {
  it('adds an SMS channel with a cap, shows the cap and the test receipt, never the token', async () => {
    const u = userEvent.setup();
    const { getApi } = renderApp({ token: 'owner-demo', route: '/settings/notifications' });
    await u.click(await screen.findByRole('button', { name: 'Add a channel' }, T));
    await u.selectOptions(screen.getByLabelText('Kind'), 'sms');
    await u.type(screen.getByLabelText('Label'), 'My phone');
    await u.type(screen.getByLabelText('Provider send URL (https)'), 'https://sms.example/v1/messages');
    await u.type(screen.getByLabelText('Provider token (never shown again)'), 'tok-not-shown');
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled(); // no number yet
    await u.type(screen.getByLabelText('Your phone number (+ and country code)'), PHONE);
    await u.clear(screen.getByLabelText('Most texts per day'));
    await u.type(screen.getByLabelText('Most texts per day'), '5');
    await u.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Cap 5 a day', {}, T)).toBeInTheDocument();
    expect(await getApi().channels()).toMatchObject([
      { kind: 'sms', secret: 'provided', config: { url: 'https://sms.example/v1/messages', to: PHONE, daily_cap: 5 } },
    ]);
    await u.click(screen.getByRole('button', { name: 'Send a test to My phone' }));
    expect(await screen.findByText('Test sent to My phone. Provider receipt: mock-0001', {}, T)).toBeInTheDocument();
    expect(screen.queryByText(/tok-not-shown/)).not.toBeInTheDocument();
  });

  it('refuses a number that is not in international form', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo', route: '/settings/notifications' });
    await u.click(await screen.findByRole('button', { name: 'Add a channel' }, T));
    await u.selectOptions(screen.getByLabelText('Kind'), 'sms');
    await u.type(screen.getByLabelText('Label'), 'Bad');
    await u.type(screen.getByLabelText('Provider send URL (https)'), 'https://sms.example/v1/messages');
    await u.type(screen.getByLabelText('Your phone number (+ and country code)'), '5550100');
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });
});
