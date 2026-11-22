# Writing OneMind tips

From the checkout, run `./tips/author check`. This one-command entry also works from elsewhere using its full path. It uses Python 3 and PyYAML. On a clean developer Mac it can install the pinned PyYAML in an isolated environment. With the built CLI and the repo's Python environment, use `onemind tips check`. Outside the checkout, pass `--root PATH`.

Run `onemind tips new` to choose a collection, a dashboard screen and a phone destination. Enter a title, the earliest compatible OS version and one to four short sentences. Ask your agent to check the result and open a draft PR. To preview your edits, run `onemind tips preview > tips-preview.html` and open that file locally. The author launcher also accepts `new` and `preview`.

Each file in `entries/` is a tip. Its filename stem is its stable ID. The YAML front matter follows `frontmatter.schema.json`. `from` and optional `until` are inclusive OS versions. `skip_if_done` lists audit events that make a tip unnecessary. The checker reads destinations from the dashboard's screen files and the phone's linking configuration. The twelve seed tips follow the Home, Approvals, Activity, Nodes, Apps, Backups, Updates, Alerts and Settings screens in the repository's demo and dashboard.

## Silent clips

Write your on-screen text yourself. For a tip called `inspect-request`, add the following front matter when its assets are ready.

```yaml
clip:
  release: tips-v1
  caption: Read the plan and check who requested the change.
```

With ffmpeg installed, run `tips/build-clip inspect-request recording.mov ../assets/tips-v1 2 10` to take ten seconds starting at second two. It builds a silent MP4, a silent WebM and a JPEG poster. Stage the outputs outside the checkout. Check and preview them with `--assets ../assets`, then attach the three files to the named GitHub release. With no assets directory, the checker downloads them from that release. Each video must fit in 3 MB and 30 seconds. Both encodings and the poster count toward the 80 MB pack budget. The preview shows the authored caption and chooses a video format using `canPlayType`.
