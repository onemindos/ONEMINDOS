---
pr: pending
branch: ma/m4-photos-on-by-default-switch
---
Photos is now on by default on every box: the library lives in the data folder unless ONEMIND_PHOTOS_DIR says otherwise, and ONEMIND_PHOTOS_ENABLED=0 stays as the operator's hard off. The owner's switch is new: GET and PUT /v1/settings/photos (PUT only files the app.enable or app.disable request, which waits in Approvals for an owner), a Photos switch in Settings under Apps, and `onemind photos settings [--on or --off] [--json]`. Refs #1232, Refs #234.
