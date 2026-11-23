---
pr: 988
branch: claude/xr-spatial-engine
---
The spatial engine for headsets (issue #814): a new /spatial page, linked from Settings › About, loads three.js and React Three Fiber in its own lazy chunk only after the readiness probe finds VR or AR, so other pages never download the 3D engine. A session starts only from the Enter VR or Enter AR button, runs through three.js's WebXRManager with an empty scene, asks for no room data and fetches nothing from outside the hub, and a frame-stats overlay shows immersive frames, frames per second, draw calls and triangles. The dashboard build now fails if three.js ever reaches a chunk every page loads. @react-three/xr was not used: its store always bundles its headset emulator (about 5.7 MB, with CC-BY-4.0 icons) even when emulation is off. Device proof on a Quest Pro is still a hand step.
