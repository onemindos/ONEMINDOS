<!-- SPDX-License-Identifier: Apache-2.0 -->
# Test a browser and headset for spatial access

This kit measures UX-9 on the device running the dashboard. Use the same device, browser, display mode and headset throughout one run. Use a charged headset with a clear play area.

1. Open your own box over trusted HTTPS. Sign in with your existing passkey if you want to test passkey behaviour. Record whether sign-in succeeded or failed. Leave it untested if you used another method.
2. Open **Settings → About → Spatial**. Check the connection, how the app was opened, and the browser’s support for immersive VR and AR. A headset may need connecting before the browser reports support. An insecure page cannot show readiness.
3. Open **Spatial diagnostics** (`/spatial/diagnostics`). Choose **Start VR test** or **Start AR test** and respond to the browser’s permission prompt. Keep tracking active until the headset exits the session. Exiting through the headset controls ends the test early.
4. For the same browser and device, choose the observed passkey sign-in outcome. **View JSON** shows the browser user agent, readiness, session mode, actual start time, measured frame rates and passkey information. The platform-authenticator capability is separate from your observed sign-in. An unknown value means the browser could not report the capability.
5. Choose **Save JSON** before starting another mode or closing the page. Record one file per device, browser, mode and display configuration. The browser saves the file locally. Sharing it is a separate manual action.

The scene draws 100, 500 and 2,000 reference markers in turn. Each FPS figure uses 90 consecutive tracked frame intervals for that load. Lost tracking restarts the current sample. Partial or unavailable measurements remain absent from the array. The benchmark measures a marker workload on this device. Complex models can have different frame costs. A declined session has no start time.

The probe uses `isSessionSupported`. Only the button calls `requestSession`, and headset animation frames supply the timings. [WebXR Device API](https://www.w3.org/TR/webxr/)
