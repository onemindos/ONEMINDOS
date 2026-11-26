// SPDX-License-Identifier: Apache-2.0

// Package cot encodes and decodes Cursor on Target (CoT) events, the XML
// messages that TAK clients (ATAK, iTAK, WinTAK, TAKX) and TAK Server use to
// share positions, markers and chat. It is the first slice of the OneMind
// "TAK native" CoT bridge (docs/architecture/TAK-NATIVE-COT-BRIDGE.md, D-032).
//
// What is here:
//   - Event, Point and Detail: the CoT event, written from the public schema
//     description (no GPL code is used or copied).
//   - Decode and Encode, with validation of the type, the how code, the three
//     times and the coordinates, and limits that keep a hostile packet from
//     costing memory (size cap, no DOCTYPE, no unknown entities).
//   - Position, a OneMind machine, sensor, camera, alert or hub location, and
//     the mapping to and from an Event. People are shared only with the
//     owner's opt-in, and a child's location never leaves the box.
//   - Sender and Receiver: a small UDP sender and receiver for the LAN
//     situational-awareness multicast group (TTL 1 by default, so packets do
//     not leave the local network).
//
// What is not here yet (later phases of the plan): the onemindd service, NATS
// subjects, the gateway policy and audit hooks, TLS links to a TAK Server, and
// TAK Protocol version 1 (protobuf). Nothing in this package is started by the
// image; it is off until a later phase wires it to a setting.
package cot
