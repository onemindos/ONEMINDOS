---
pr: pending
branch: fix/recovery-td1-boot
---
Recovery mode now actually starts when the data disk is missing. In the QEMU runs the boot with the data partition renamed never reached onemind-recovery.target: the isolate that onemind-data-check.service triggers pulls local-fs.target in again, which started the check again, which failed again and isolated again, in an endless loop of 30-second data-device waits, so TD1 never saw the recovery console line. The check now skips itself once its status file exists. The serial-log trimmer also keeps start-job timeouts, failed dependencies and OnFailure triggers, so a loop like this shows in CI logs.
