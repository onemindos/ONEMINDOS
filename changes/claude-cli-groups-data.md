---
pr: pending
branch: claude/cli-groups-data
---
The onemind command line gains groups for your files and photos and for how you hear about things. `files` browses your spaces, folders, trash and space limits, requests giving an app or an AI agent a folder or emptying a trash (an owner approves in the dashboard, the CLI never does), and lists requests and grants. `photos` shows the library and, for each phone, how many photos are on the box, in a backup and in a backup that was test-restored. `onboarding` shows first-run progress and saves the first-run choices. `notify prefs` shows and changes quiet hours, digest and muted topics without losing the rest of your settings, and `notify sources` lists and mutes the apps that send you things. Every command takes --json. Refs the UI and backend parity report (S3 and S8 CLI rows).
