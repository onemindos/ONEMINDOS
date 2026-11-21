---
pr: pending
branch: claude/hub-jetstream-streams
---
First slice of JetStream on the hub for app event streams. The hub NATS now has a file-only JetStream store on the data disk (a bind mount from /data, 4 GiB cap, no memory store), and the hub account gets the same cap in the generated accounts file while node accounts get none. An app can declare `spec.streams` (name, relative subjects, a required byte limit and age limit, both bounded); the hub places subjects under onemind.app.APP_ID so an app cannot touch core subjects. The install plan lists every stream with its exact limits and hashes them, so the owner approves them. An install is refused with a clear reason when a declaration is invalid or when the store is off or nearly full (degraded). Creating the streams on the hub after approval is the next slice.
