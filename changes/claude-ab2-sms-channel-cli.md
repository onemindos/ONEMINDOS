---
pr: 934
branch: claude/ab2-sms-channel-cli
---
SMS alert channel, part 2 (#869): the SMS channel is now reachable from Settings, Notifications (pick Text message, type your number, the provider's HTTPS send URL, its token and the most texts per day; the cap shows on the channel and a test shows the provider receipt or the plain error) and from the CLI: onemind notify channel add sms (the provider token is asked for without echo or read with --secret-stdin, never a flag), onemind notify channel list (with the daily cap) and onemind notify test sms. The dashboard's test-send type now matches what the gateway answers.
