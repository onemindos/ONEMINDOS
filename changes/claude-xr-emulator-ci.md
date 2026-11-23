---
pr: 942
branch: claude/xr-emulator-ci
---
WebXR emulator tests (issue 813): IWER (MIT) stands in for a Quest Pro and a Quest 3 in the tests/e2e Playwright suite. A new spatial project enters and exits immersive-vr and immersive-ar on /spatial/diagnostics of the real e2e hub under both profiles, with scripted controllers and hands, and asserts page state and draw counts (three.js renderer.info shape), never FPS. A reusable helper (tests/e2e/lib/xr.ts) and a vitest kit for the spatial screens (dashboard/src/screens/spatial/xrTestKit.ts) let later XR work test the same way. New workflow xr-emulator.yml runs it on spatial changes and nightly; real Quest Pro proof stays a hand step.
