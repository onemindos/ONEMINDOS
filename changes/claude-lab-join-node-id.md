---
pr: pending
branch: claude/lab-join-node-id
---
Lab finding from the R530 run: after a successful join, onemindd kept publishing heartbeats under the random id firstboot wrote before the join, while the leaf account and fabric.json used the id the join registered, so the hub showed the node as joining with no leaf link. The join now writes ONEMIND_NODE_ID (the joined id) into onemindd.env before it restarts onemindd, replacing the old value. The node name offered on the approval card now comes from the seed (firstboot state) when the owner chose one, instead of always the machine's hostname.
