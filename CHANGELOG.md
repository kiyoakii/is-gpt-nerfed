# Changelog

## Unreleased

- A second check next to the fingerprint: every probe first asks Codex's backend which model it says answers a
  request for the session's model and effort (the `OpenAI-Model` header Codex itself checks, or `response.model` in
  the first event), then closes the connection. The fingerprint still runs every time. The server's answer can raise
  a verdict but never clear one: a Match it contradicts becomes Suspicious, a downgrade it admits to decides when
  the fingerprint has no verdict of its own, and a Mismatch stands whatever the server says. An upgrade, a name the
  catalog does not list, and a failed check are reported next to the verdict and change nothing. The panel shows it
  in the row and in the report, in English and Chinese; `nerfed served` runs the check alone; Settings and
  `served_check` switch it off. The access token is used only while its JWT is valid and only against a fixed URL
  with redirects refused; the refresh token is never read. Thanks to @LamWS for the idea and the first version.
- `nerfed config set` now stores `served_check` as a boolean; a value typed as `false` used to be kept as a string
  and read as true.

## 0.5.1 — 2026-09-18

- The 0.5.0 app crashed at launch on every Mac except the one that built it: the localization looked its resource
  bundle up through SwiftPM's generated accessor, which only checks the .app root and the build machine's absolute
  path. The bundle is now located explicitly (Contents/Resources first) and a missing bundle falls back to English
  instead of trapping. Reported and fixed by JoyboyBrian (#2, #4).
- `nerfed` linked into ~/.local/bin by install.sh failed with "No such file or directory": the wrapper resolved the
  repository from the symlink's own path. It follows the symlink first now. Reported and fixed by JoyboyBrian (#3, #5).
- The 30-minute schedule missed sessions: the hooks only ran it at the end of a turn, so a session that went quiet
  before its due time (or whose last turn ended in an error, which fires no Stop hook) was never probed, and the
  panel showed it as "due" forever. The app now runs `nerfed tick` when the snapshot shows a thread that is due and
  active, and the tick launches the same background probe the Stop hook would. Threads quiet for more than 15
  minutes are left alone.

## 0.5.0 — 2026-09-18

- The app speaks Simplified Chinese: the panel, settings, evidence lines, progress and error messages follow the
  system's preferred languages, with English as the fallback. Model IDs, reasoning-effort values and your own session
  titles stay as they are; stored records, CLI output and notifications are unchanged. A Chinese README
  (README.zh-CN.md) came with it. Contributed by sudoHG (#1).
- `nerfed selftest` crashed on its own synthetic analysis; an analysis without candidates is now Invalid instead of
  an error.
- The hooks' fallback path points at the plugin's source (the checkout or the app bundle) instead of a Codex cache
  directory, so hooks keep working after a version bump makes Codex delete the old cache.

## 0.4.4 — 2026-09-16

- A failed attempt no longer sends a notification; it is logged and the row offers Retry. Codex's transient
  "thread history projection is behind durable rollout" store error counts as transient: one retry after a pause.
- config.json keeps only the settings you changed, so new defaults apply after an update.

## 0.4.3 — 2026-09-16

- A fork that has not answered within the deadline (now 300 s) is replaced once, so a slow model does not drop out of
  the sample and leave the verdict to whichever model answered fast. The record says so (`topped_up`).
- A Mismatch needs at least two answers; a single answer only ever reaches Suspicious.

## 0.4.2 — 2026-09-16

- Probes identify themselves to the service as the client they check for: the probed session's own originator
  (`Codex Desktop`, or `codex_cli_rs`), instead of the probe's clientInfo name. If routing depends on the client, the
  probe now sees what the desktop sees. `probe_originator` in the config and `--originator` on `probe now` / `probe
  fresh` override it for A/B tests; the report says which client a probe ran as.

## 0.4.1 — 2026-09-15

- "Session" everywhere the panel, the CLI and the docs speak to people (Codex's API keeps calling them threads).
  The default schedule is every 30 minutes of activity per session instead of every 8 turns.
- Panel: click a session (or the fresh-session row) and the lines under its title slide aside for its report:
  last verdict, fingerprint, probe facts, earlier probes, evidence with what was reverted, Copy report; nothing
  else moves. Right-click for Probe, Copy report, Reveal folder. Settings is a page of its own. Fresh session sits
  below the threads; the header is the chip face with one short line per fact; the panel is a little narrower.
  The Report window is gone (the report lives in the rows; `nerfed report` remains).
- Self-update: every 10 minutes the app asks GitHub for the latest release tag (one request; `check_updates`
  switches it off) and shows "vX.Y.Z is out · update" in the footer, with one notification per new version. Clicking
  it downloads the release zip, verifies its sha256, replaces the app (the old copy goes to the Trash) and relaunches
  (`nerfed update-install`). Failed checks are silent. `build.sh --dmg` makes a disk image for first-time downloads;
  `build.sh --release` signs with a Developer ID, notarizes and staples both (SIGN_IDENTITY, NOTARY_PROFILE).
  `install-app.sh` installs the latest release from Terminal with the checksum verified and no Gatekeeper block.
- "Open folder in Finder" (right-click) now opens the thread's folder; it used to only activate Finder, which showed
  whatever window was in front.
- Copy report moved to the row's right-click menu. The prompt-language row left Settings: the probes use
  ModelTrace's own zh and en prompt texts, its default; `languages` stays as a config key.
- Upgraded: a move to a better model (a rollout such as gpt-5.6-sol → gpt-6-sol) is a state of its own, shown in green
  and notified, from the passive scanner or the fingerprint. Better or worse is decided by `compare_models`, not a
  fixed list: Codex's catalog succession pointer, hidden internal models, the generation and size tier in the slug,
  then Codex's own ranking, the highest supported reasoning effort and the context window.
- The headline is "All clear" unless something is downgraded or suspicious; an unverified count (a verdict from
  another account, or from before accounts were tracked) follows on the next line instead of being the headline.
- Fixed: the SessionStart hook crashed (silently, in the fail-safe) on a keyword collision, so session starts were
  not logged.
- A failed attempt (Invalid) is no longer shown as a verdict: the row keeps its last verdict and offers Retry; the
  report notes the attempt. A verdict from another account reads "Unverified · Match, another account"
  instead of a greyed-out Match.
- Probes: a Suspicious first round no longer triggers a second one by default (`confirm_uncertain` is opt in), so a
  probe costs three answers.
- Scanner: Codex's usage-limit snapshot in the rollout is not read as a serving signal (it is the last limit family
  Codex parsed from the headers, not the bucket the turn was charged to); the "at the usage limit" label only uses
  the default family.

## 0.4.0 — 2026-09-15

First public release.

- Passive scanner: silent model / reasoning-effort / context-window changes and hidden internal models, read from
  the thread's own rollout on every turn (zero tokens).
- Active probe: three parallel `ephemeral: true` forks of the thread through Codex's app-server, attributed with
  ModelTrace's calibrated fingerprint bank; confidence-gated verdicts (Match / Suspicious / Downgrade / Downgraded /
  Unlisted / Invalid) with an automatic confirmation round and one automatic transport retry.
- Busy threads are forked at their newest finished turn, or waited for.
- Fresh-session probe: what does a brand-new session get right now?
- Accounts: probes are tagged with a hash of the signed-in Codex account; verdicts from another account (or from
  before tracking) are shown as unverified and re-probed.
- Hook trust: `nerfed hooks status|trust`; the installer offers to record trust (Codex skips untrusted hooks silently).
- Activity log (`nerfed log`), report, explain, evidence, audit.
- Menu bar app for macOS 26 (Liquid Glass): status, fresh session, active threads with verdicts and evidence,
  settings, report; red paw on a confirmed downgrade, orange when suspicious. Screenshot mode hides thread titles.
  The plugin is bundled inside the app, which installs it into Codex on first run.
- `nerfed probe now` opens an interactive session picker (vendored simple-term-menu) when run from a terminal.
- Fresh-session heartbeat (`fresh_frequency`): probe a brand-new session every N minutes regardless of activity.
- Hooks are fail-safe: the entry point never exits non-zero, and reinstalls keep previous version paths resolvable.
