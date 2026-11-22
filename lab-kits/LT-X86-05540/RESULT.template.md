# LT-X86-05540 result
- Date / tester: <date> / founder
- Device: Dell Latitude 5540, BIOS <version>, RAM <GB>, disk <type/size>   (no serial numbers)
- Software: kit commit <sha>; Leg W: Windows <build>, OneMind desktop <version>; Leg L: Debian 13 live <image date>, kernel <version>
- Hub: <model>, OneMind <version>, same LAN, address recorded as <hub-ip>
- Criteria: README "Pass / fail" in this kit (no row in 22)
- Result: PASS / FAIL / BLOCKED (<exact reason>)

| # | Step | Result | Numbers / notes |
|---|---|---|---|
| 1 | Pair, Leg W and Leg L | PASS / FAIL | first-time pairing yes/no; token location |
| 2 | Dashboard and desktop app | PASS / FAIL | first screen load <s>; layout breaks at 1366x768 |
| 3 | Wi-Fi and Bluetooth toggle, reboot | PASS / FAIL | hub UP after Wi-Fi back <s>; headset reconnect yes/no |
| 4 | Audio and webcam | PASS / FAIL | sink/source/video0 listed yes/no |
| 5 | Sleep and wake (battery, charger) | PASS / FAIL | success +<n>, fail +<n>; wake time <s>; hub UP <s> |
| 6 | Dock and displays | PASS / FAIL | mirror / extend / lid closed / undock |
| 7 | WAN loss | PASS / FAIL | hub UP polls <n>/<n>; app recovery <s> |

- Notes / surprises:
- Decision consequence applied: none (client issues only)
