<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lock-screen approvals and Lock OneMind device check

Refs #704 and #909. Run on an Android 14 phone and an iPhone with a PIN and biometrics enrolled. Install native builds made from the PR head, allow OneMind notifications, and sign in as an owner on a test hub with an enrolled approval credential.

- **Android 14:** Register a UnifiedPush distributor. For the closed-app run, exit OneMind before queuing the requests and use the generic notification supplied by UnifiedPush.
- **iPhone local notifications:** Open OneMind and let it finish its first refresh. Queue the requests from another client, then refresh OneMind while it is still open. Confirm both new approval notifications appear in Notification Center before locking the phone. For the cold-start run, close OneMind after the notifications arrive, then tap Review on one of those notifications.
- **iPhone remote push:** The gateway in this build rejects APNs registrations. Track remote delivery and the Review and Deny buttons on a remotely delivered notification separately under #704 and [#208](https://github.com/onemindos/ONEMINDOS/issues/208).

1. Queue two harmless test requests with the same title and different request IDs. Lock the phone. The actionable notification should offer Review and Deny. The operating system should require unlock for either button. Check that no notification button approves anything.
2. Tap Review on the older request. Verify that the older card opens expanded and the newer card stays collapsed. Check the action ledger from a second client. Both requests must still be waiting. Repeat with OneMind running in the background and with a cold start. On Android, verify the cold-start case from the generic UnifiedPush notification. Also tap an approval notification body and verify it performs no decision.
3. On the card, attempt to approve using a test request that requires a signed biometric approval. Cancel the signing prompt and check that the request is still waiting.
4. Lock the phone and tap Deny. Unlock the phone, then cancel OneMind’s request-specific confirmation. Verify that no Deny appears in the ledger. Tap Deny again and complete the confirmation. Check that the prompt identifies the title and request ID, that the targeted request becomes cancelled once, and that the other request stays waiting.
5. Deny the second request from another client, then try its original notification's Deny button. The OS may still request device unlock. OneMind should report that the request is no longer waiting without asking for a Deny confirmation.
6. In Settings, turn on **Lock OneMind**. Cold launch and cancel the unlock. Share a small test file into OneMind and verify the share sheet and its folder list appear only after unlocking the app.
7. With an approval card visible, open the app switcher. The preview must hide the card. On Android, screen capture is blocked while Lock OneMind is enabled. Switch back within 30 seconds and check that the app resumes without another prompt. Repeat after at least 30 seconds and check that OneMind prompts before exposing the card. Turn the lock off and verify the change requires confirmation.

| Device | App commit and hub version | Steps 1–7 | Sanitized evidence |
| --- | --- | --- | --- |
| Android 14 | Pending | Pending | Pending |
| iPhone (local notifications) | Pending | Pending | Pending |
| iPhone (APNs delivery and actions) | Pending | Blocked on APNs support | Pending |

Record the OS versions, per-step results, and relevant request states. Keep credentials, hub addresses, and personal screenshots out of public evidence.
