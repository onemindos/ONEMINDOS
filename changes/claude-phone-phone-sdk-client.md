---
pr: 831
branch: claude/phone-phone-sdk-client
---
The Android and iPhone app now talks to the hub through the generated gateway client (@onemind/sdk), the mobile slice of CI-08: every JSON request goes out through OneMind.call and screens can reach the client as HttpApi.sdk, while the phone keeps its own error messages, session renewal and answer checks. The SDK is bundled from its source by Metro and Jest the way the dashboard does it, and a compile-time contract checks the phone's types against the generated schema, so renaming a gateway field now fails the phone's typecheck. That check already found one drift: the gateway sends the approval card object in an action's approval field, which crashed the Activity screen; the screen now shows the method only when the hub sends one. System controls stay hidden and send nothing, since the hub has no plan preview for them. The camera (no microphone) and the biometric prompt are added for wave P, with their permissions.
