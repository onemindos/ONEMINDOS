---
pr: pending
branch: claude/201-industrial-adapters
---
FLD-03 (#201): four observe-first field protocol adapter apps, Modbus TCP, BACnet/IP, OPC UA (SecurityPolicy None, anonymous) and CAN through socketcand, each reading device values and publishing them on NATS as tel.<node>-<device>.<class>.<metric> with a read-only status page. They are OneMind's own standard-library Python on the pinned python image, written from the public specifications. Writes are always refused until the gateway publishes owner-approved cmd actions. test/unit/test_field_adapters.py runs each adapter against an in-process simulator of its protocol and proves only read requests reach the wire. Known gap: the per-app network policy still blocks LAN devices and NATS on a box.
