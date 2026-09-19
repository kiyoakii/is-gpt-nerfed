# Development notes

## Layout

| path | |
| --- | --- |
| `plugin/` | the Codex plugin: `.codex-plugin/plugin.json` (manifest + hooks), `skills/is-gpt-nerfed/` (SKILL.md, `scripts/nerfed`, `codex_appserver.py`, `modeltrace_core.py`, `vendor/`), `assets/` (ModelTrace bank + provenance, logo) |
| `.agents/plugins/marketplace.json` | makes the repository a local Codex marketplace |
| `macos/` | SwiftUI menu bar app (macOS 26). `build.sh --install` / `--run` / `--zip` / `--dmg` / `--release`; the plugin is copied into the bundle so the app can install itself |
| `bin/nerfed`, `install.sh`, `uninstall.sh` | the CLI wrapper and the plugin-only install |
| `install-app.sh` | one-line install of the latest release (curl, checksum, no quarantine flag) |
| `tests/` | unit + offline end-to-end tests with a fake app-server (`fake_codex.py`); `test_parity.py` checks the scorer against ModelTrace's JS core (needs node) |
| `tools/set_icon.sh` | adopt a 1024×1024 PNG as app icon and plugin logo, rebuild |

`nerfed` is one Python 3.9+ script, standard library only, run by the system `python3`. Nothing is compiled except the app.

```bash
python3 -m unittest discover -s tests -v
./bin/nerfed selftest
./macos/build.sh --install          # Xcode 26
NERFED_DEMO=1 ~/Applications/IsGPTNerfed.app/Contents/MacOS/IsGPTNerfed --render docs/panel.png   # README images
```

## The server check (`served_check`)

`responses_meta.check_served_model()` makes one streaming POST to `https://chatgpt.com/backend-api/codex/responses`
with the model and reasoning effort the probe is about to fingerprint, reads the model the server names, and closes
the connection at the first event. `ask_server()` runs it before the forks on both probe modes and stores it on the
record as `served`; `nerfed served` runs it alone.

- Two places carry the name. `OpenAI-Model` (response header) is the one Codex itself reads: it turns into
  `ResponseEvent::ServerModel`, and a difference from the requested model logs "server reported model X while
  requested model was Y" and raises `ModelReroute` (the gpt-5.3-codex → gpt-5.2 cyber-activity reroute). Codex does
  not read `response.model` from the `response.created` event, which is the Responses API's own field. The check
  prefers the header and falls back to the body.
- On this maintainer's Mac the header has never appeared: 0 occurrences of "server reported model" or "openai-model"
  in 675k rows of `~/.codex/logs_2.sqlite` (10 days, 547 header dumps), including the hours when probes fingerprinted
  luna for an astra session. Codex never logs response bodies, so what `response.model` said then cannot be checked.
  Treat the check as a second opinion of unproven yield, not as a detector in its own right.
- `x-codex-safety-buffering-*` is not used: the `faster-model` header was present on every response in those logs
  (25/25 and 9/9 sampled), so it discriminates nothing.
- Token rules: the ChatGPT access token from `auth.json` is read only while its JWT `exp` is in the future and is
  sent only to the module's constant URL — no environment override, and redirects are refused (`_NoRedirect`),
  because urllib would otherwise repeat the Authorization header to wherever a 3xx points. The refresh token is
  never read (OpenAI rotates it on use; consuming one would break the user's Codex login). The request carries
  `ChatGPT-Account-Id` as Codex does, identifies as the probe's originator, and names itself in the User-Agent.
- `server_finding()` reads the answer: `same` (a dated snapshot such as `gpt-6-astra-2026-08-20` counts as the model
  asked for), `downgrade` / `upgrade` / `lateral` through `compare_models`, `unrecognized` for a name neither the
  catalog nor the bank knows, `failed` for no answer.
- `combine_with_server()` weighs it. The server can raise a verdict, never clear one: a Match it contradicts becomes
  Suspicious, and a downgrade it admits to decides when the fingerprint reached no verdict (no answers, an unlisted
  model, a Suspicious lean). An upgrade, an unrecognized name and a failed check change nothing. A fingerprint
  Mismatch stands whatever the server says, because a swap that keeps the name is what the fingerprint is for.
- The check answers for the account at that moment, not for the session being probed: it is a bare request with no
  history. That is why it may not clear a verdict, only raise one.

## Localization

The macOS presentation layer supports English and Simplified Chinese (`zh-Hans`), using localized
`Localizable.strings` and `Backend.strings` resources packaged by SwiftPM. English is the development language and fallback.
The app follows the user's preferred languages; restart the app after changing the system or per-app language.

Keep translations in the presentation layer. Do not translate JSON keys, verdict codes, model IDs, configuration
values, or ModelTrace's calibrated probe prompts. Localize app-generated evidence, diagnostics and progress text
at presentation time, retaining their original stored values. CLI output and plugin notifications are unchanged.
Unknown external messages must remain readable instead of disappearing or being assigned a different verdict.
Translate synthetic demo titles only when `snapshot.demo` is true; never translate a user's real session title.

When adding a language, add both matching string tables under its `.lproj` directory with the same keys and compatible
format placeholders, and list the locale in `CFBundleLocalizations` in `macos/Info.plist`. Extend the backend template
translator for that language; it currently preserves English and unsupported languages verbatim. Reasoning identifiers
such as `high`, `xhigh` and `max` must remain unchanged in all languages.
Test both SwiftPM execution and the assembled `.app`: the release bundle needs the SwiftPM
resource bundle as well as the executable. Check the panel, expanded report and settings at their existing width
and type scale, using synthetic data (`NERFED_DEMO=1`). Set `NERFED_HOME` to a temporary directory and `NERFED_BIN`
to the checkout's CLI for these previews, because even `snapshot --demo` writes a ledger and CLI path hint.

The English and [Simplified Chinese README](../README.zh-CN.md) should describe the same behavior; command names,
configuration keys and URLs stay unchanged in translations.

## How Codex runs the plugin

- `codex plugin add` copies the plugin to `~/.codex/plugins/cache/is-gpt-nerfed/is-gpt-nerfed/<version>/` and exports
  `PLUGIN_ROOT` (that path) to hook commands, so hooks run the cached copy. After changing code, copy the changed
  files into the cache or run `./install.sh`. When the manifest version changes, Codex Desktop re-caches on its own and
  drops the old version directory; `~/.codex/is-gpt-nerfed/plugin` is kept as a stable fallback path for the hooks.
- Hook trust: Codex silently skips hooks it has not been told to trust. Trust is a per-definition hash under
  `[hooks.state."<hook key>"]` in `~/.codex/config.toml`, written through the app-server's `config/batchWrite`, the same
  call the Codex TUI's `/hooks` screen makes (`nerfed hooks status` / `nerfed hooks trust`). The hash covers the hook
  command, so changing a command needs re-trusting; `install.sh` does that.
- A non-zero exit from a hook (argparse's exit 2 included) makes Codex block the user's turn. The hook entry point
  therefore never exits non-zero, and the shell wrapper exits 0 when `python3` or the script is missing. A hook that
  crashes is recorded in `~/.codex/is-gpt-nerfed/errors.log` and nowhere else.

## Probes

- `codex_appserver.py` talks JSON-RPC to a private `codex app-server --stdio` (hooks and notifications disabled in that
  process): `thread/read`, `thread/turns/list`, `thread/fork` with `ephemeral: true` at the newest finished turn,
  `turn/start` per fork, collect the final agent message. Server-initiated requests (approvals) are refused.
- A session whose newest turn is live cannot be forked at that turn (`identifies an in-progress turn`); the previous
  finished turn is used, else the probe waits up to `busy_wait_s` (600 s) and reports a retryable Invalid.
- One automatic retry on transport failures. A fork that has not answered within `probe_timeout_s` (300 s) is
  replaced once (`topped_up` in the record), so that a slow model does not drop out of the sample. A Suspicious
  verdict stands until the next probe; `confirm_uncertain` (off by default) adds one more round of three answers.
- Verdict gate (`mismatch_confidence` 0.8): Mismatch needs p(top) ≥ 0.8, p(declared) ≤ 0.2, a fused z-score margin
  ≥ 0.5σ (ModelTrace's calibrated softmax amplifies small gaps) and at least two answers (one answer is calibrated
  at 95.5 %).
- Fresh-session probe: `thread/start` with `ephemeral: true`, no history.
- The desktop's `/side` is a `thread/fork` too, with whatever model its picker is set to; the probe forks with the
  parent's model and effort. Whether the two requests are byte-identical cannot be checked: the desktop's fork
  parameters are not logged, and Codex never logs request bodies.
- The desktop also starts ephemeral helper threads of its own (its suggestions generator: "Generate 0 to 3
  hyperpersonalized suggestions…") on gpt-5.6-terra. They fire the hooks like any session; the ledger files them
  as `side` because they have no rollout, and the panel never lists them. They are not side chats.
- Every request Codex makes carries an originator (the desktop app: `Codex Desktop`; the CLI: `codex_cli_rs`); a
  session started through the app-server would carry the client's `clientInfo` name instead. The probe process sets
  `CODEX_INTERNAL_ORIGINATOR_OVERRIDE` to the probed session's originator (or the binary's owner for fresh probes),
  so the service sees the same client. `probe_originator` and `--originator` override it for A/B tests.
- The zh and en prompts are ModelTrace's own texts, verbatim. Its bank was enrolled under twelve unnamed conditions and
  its author calls other languages uncalibrated, so the prompt language is not a user setting (`languages` stays as a
  config key).

## Passive scanner

Reads the session's rollout JSONL incrementally on every Stop hook.

| finding | severity | trigger |
| --- | --- | --- |
| `silent_model_change` | hard / good | `turn_context.model` changed with no `thread_settings_applied`: hard for a downgrade, good for a confident upgrade, soft otherwise |
| `applied_model_change` | soft / good | the same change applied through thread settings: soft for a downgrade ("was that you?"), good for an upgrade |
| `silent_effort_change`, `applied_effort_change` | hard / soft | reasoning effort dropped, silently or through settings |
| `hidden_model` | hard | a model with `visibility=hide` in `models_cache.json` ran a turn |
| `context_window_change` | hard | `token_count.info.model_context_window` shrank |
| `service_tier_change` | info | priority tier dropped |

Only the latest change per dimension (model, effort, context window, tier) is active; a reverted change stays in the
log and the report. `compare_models` decides whether a model switch is an upgrade or a downgrade from these signals,
most trusted first: the catalog's successor pointer (`upgrade` in `models_cache.json`), hidden internal models, the
generation in the slug (gpt-5.6 → gpt-6, claude-opus-4-7 → 4-8), the size tier in the slug (nano,
mini/spark/lite/small/flash, plain, pro/ultra), the catalog's ranking (`priority`), the highest supported reasoning
effort, and the context window. Each answer carries a confidence, and only upgrades with high or medium confidence
are reported.

`token_count.rate_limits` is not the bucket a turn was charged to and says nothing about the model that answered:
Codex parses one snapshot per limit family from the response headers in alphabetical order (`codex`, then e.g.
`codex_bengalfox`, the GPT-5.3-Codex-Spark allowance) and persists the last one. The bucket a turn was charged to is
in the server's `x-codex-active-limit` header, and no header names the model that answered, so the fingerprint is the
only measurement of that. The scanner reads `rate_limits` only for the "at the usage limit" label, and only from the
unnamed default family.

## Ledger (`~/.codex/is-gpt-nerfed/`)

| file | |
| --- | --- |
| `log.jsonl` | activity log, one JSON object per line: `account_switch`, `probe_due`, `worker_spawn`, `probe_start`, `probe_round` (per-fork model/effort/tier/timing/usage), `probe_wait`, `probe_retry`, `probe_verdict` (candidate list), `scan_finding`, `hooks_trust`, `config_set`, `status_change`, `update_check`, `error`. `nerfed log --since 2h --kind probe_verdict --json` |
| `probes/*.json`, `probes.jsonl` | full probe records (every fork's answer text) and the index |
| `sessions/*.json` | per-session schedule state, evidence, alerts |
| `events.jsonl` | raw hook event metadata |
| `account.json`, `hooks_status.json`, `state.json`, `update.json` | last seen account, cached hook trust, last panel status, last release check |

The app also logs to the unified log (Console.app, subsystem `is-gpt-nerfed`).

## Full configuration

| key | default | |
| --- | --- | --- |
| `frequency` | `30m` | `Nm`, `Nh` (of activity), `turns:N`, `manual` |
| `fresh_frequency` | `manual` | `Nm`, `Nh`, `manual` |
| `mode` | `auto` | `auto` / `nudge` |
| `queries` | `3` | forks per probe, 1–3 |
| `parallel` | `true` | forks run concurrently |
| `languages` | `zh,en` | prompt language pool (ModelTrace's texts) |
| `passive` | `true` | rollout scan on every turn |
| `notify`, `notify_on_ok` | `true`, `false` | macOS notifications |
| `announce_ok` | `false` | push Match verdicts into the session |
| `sound` | `true` | Codex notification sound on a downgrade |
| `halt_on_mismatch` | `false` | deny work tools after a mismatch until `nerfed resume` |
| `mismatch_confidence` | `0.8` | verdict gate |
| `confirm_uncertain` | `false` | second round when Suspicious |
| `probe_timeout_s` | `300` | seconds a fork may take; a timed-out fork is replaced once |
| `busy_wait_s` | `600` | how long to wait for a live turn |
| `hide_titles` | `false` | screenshot mode |
| `check_updates` | `true` | ask GitHub for a newer release every 10 minutes |
| `codex_bin` | auto | path to the codex binary (found on PATH or inside the ChatGPT/Codex app) |

## Release

```bash
./macos/build.sh --zip && ./macos/build.sh --dmg        # dist/IsGPTNerfed-<version>.{zip,dmg} + .sha256
gh release create v<version> dist/IsGPTNerfed-<version>.* --title <version>
```

The tag must be `vX.Y.Z` and the release must not be marked pre-release, because the app and `install-app.sh` read
`releases/latest`. The app checks every
10 minutes (`nerfed update-check`, state in `update.json`) and shows "vX.Y.Z is out · update" in the footer, one
notification per version. Clicking it runs `nerfed update-install` detached: download the zip, verify its sha256, stop
the app, move the old bundle to the Trash, put the new one in place, strip quarantine, relaunch. A failed check is
silent; a failed install shows "Update failed · retry". Codex also accepts the repository as a git marketplace
(`codex plugin marketplace add kiyoakii/is-gpt-nerfed`, `codex plugin add is-gpt-nerfed@is-gpt-nerfed`).

### Signing and notarization

Not done yet. It needs an Apple Developer Program membership, and an individual's certificate carries their legal
name. Until then the app is ad-hoc signed; `install-app.sh` and the self-updater avoid the Gatekeeper block, and a
browser download needs System Settings → Privacy & Security → Open Anyway. With a Developer ID:

1. Xcode → Settings → Accounts → Manage Certificates → + → **Developer ID Application**;
   `security find-identity -v -p codesigning` then lists it.
2. `xcrun notarytool store-credentials nerfed-notary --apple-id <email> --team-id <TEAMID> --password <app-specific password>`.
3. `SIGN_IDENTITY="Developer ID Application: Name (TEAMID)" NOTARY_PROFILE=nerfed-notary ./macos/build.sh --release`
   signs (hardened runtime, timestamp), notarizes and staples the zip and the dmg; `spctl -a -vv` must end with
   `source=Notarized Developer ID`.

## Limits and contributions

Windows and Linux are untested. The Python is portable, but notifications and the app are macOS-only. Codex's
app-server protocol is marked experimental; `nerfed doctor --fork` checks the fork path against the installed Codex
without running inference. Contributions that would help most: new detection signals, bank updates from upstream
ModelTrace (keep `provenance.json` accurate), and Windows or Linux support. Keep the panel to its type scale (17 / 13 /
11) and without icons.
