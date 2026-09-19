<p align="center"><img src="docs/social-preview.png" width="880" alt="is-gpt-nerfed: shrinkflation detector for Codex"></p>

English · [简体中文](README.zh-CN.md)

You pick a model in Codex. This tells you whether that model is actually the one answering. If it isn't, you get this:

<p align="center">
  <img src="docs/nerfed-sticker.png" width="220" alt="">
  <br>🎉 Congrats! You've been nerfed! You asked for gpt-6-astra; the fingerprint says gpt-5.6-luna (91%). Enjoy the discount you didn't ask for.
  <br><sub>Example output, not a real verdict.</sub>
</p>

<p align="center">
  <img src="docs/panel.png" width="48%" align="top" alt="Menu bar panel: status, active sessions with verdicts, fresh-session probe">
  <img src="docs/panel-detail.png" width="48%" align="top" alt="A session opened in place: fingerprint, earlier probes, evidence">
  <br><sub>The panel, and a session opened in place. Sample data, not real sessions.</sub>
</p>
<p align="center">
  <img src="docs/face-ok.png" width="72" alt="all clear"> <img src="docs/face-warn.png" width="72" alt="suspicious"> <img src="docs/face-alert.png" width="72" alt="nerfed">
  <br><sub>All clear · Suspicious · Nerfed</sub>
</p>

## What it checks

The analysis runs on your Mac and your records stay there. Two of the three checks below cost nothing; the third
asks Codex for answers through your own account.

Codex records, for every turn, which model and reasoning effort it asked for. The plugin reads those records after
each turn and flags what changed without you changing it: a model swap, a lower reasoning effort, a hidden internal
model such as `gpt-reserve`, a smaller context window. A move to a newer or larger model is reported as well, since
a rollout can go either way. This costs no tokens.

On a schedule, the plugin also forks your session three times, ephemerally, through the same app-server call the
desktop uses for a side chat, with the session's own model and reasoning effort. Each fork is asked for about 300
"random" numbers. A language model picks random numbers with a bias that is characteristic of the
model. [ModelTrace](https://github.com/xqy2006/ModelTrace)'s calibrated bank turns the three answers into a
fingerprint (100 % accuracy with three answers in cross-validation), and the verdict compares that fingerprint with
the model you selected.

Each probe also asks the server itself. One small request for the same model and reasoning effort goes to Codex's
backend, and the server names a model in its answer, either in a response header that Codex itself checks or in the
first event of the stream. The connection closes there. That name is a label, so it is weighed next to the
fingerprint rather than instead of it: when the server names another model it is taken seriously, and when it names
the model you asked for it proves nothing, because a swap that keeps the name is exactly what the fingerprint is
for. `nerfed served` runs the check on its own, and `served_check` switches it off.

| verdict | meaning |
| --- | --- |
| Match | the model you selected answered |
| Suspicious | the fingerprint leans elsewhere but not confidently, or it matches while the server names another model |
| Downgrade / Upgrade / Rerouted | a confident mismatch: top candidate at 80 % or more, your model at 20 % or less, at least two answers |
| Downgraded | Codex's own records show a silent switch, or the server named a lesser model and the fingerprint could not settle it |
| Upgraded | Codex's own records show a move to a newer or larger model |
| Unlisted | your model is not in the fingerprint bank yet |
| Invalid | no usable answer (tool use, refusal, network); not a verdict, the row keeps its last one and offers Retry |

A mismatch reaches you as a macOS notification, a message in the session, and a red face in the menu bar. A match is
not announced.

## Install

macOS 26. One line in Terminal installs the latest release and opens it:

```bash
curl -fsSL https://raw.githubusercontent.com/kiyoakii/is-gpt-nerfed/main/install-app.sh | sh
```

You can also download the disk image from [Releases](https://github.com/kiyoakii/is-gpt-nerfed/releases) and drag
IsGPTNerfed to Applications. The app is not notarized yet, so macOS blocks that first launch until you allow it under
System Settings → Privacy & Security.

Click the face in the menu bar and press **Install**. That registers the bundled plugin with Codex and trusts its
hooks. When a newer release is out, the footer says so and a notification arrives once; click it and the app downloads
the new build, checks its checksum, replaces itself and relaunches.

Without the app, on any macOS:

```bash
git clone https://github.com/kiyoakii/is-gpt-nerfed ~/is-gpt-nerfed && cd ~/is-gpt-nerfed && ./install.sh
```

Say yes when it asks to trust the hooks. Codex runs no hook you have not trusted, and it does not tell you.

Requires a Codex with plugin hooks (desktop app or CLI; tested on 0.154) and the system `python3`. `./uninstall.sh`
removes everything.

## Using it

The macOS interface supports English and Simplified Chinese, following the system's preferred languages with
English as the fallback. This includes app-generated evidence, progress messages and diagnostics shown by the
app. User session titles, model IDs, reasoning-effort values and unrecognized external diagnostics keep their
original text. Stored records, CLI output, notifications and ModelTrace's calibrated probe prompts are unchanged.

Every session you work in is probed in the background after 30 minutes of activity: the hooks run the schedule
after each turn, and the menu bar app catches a session that goes quiet right after its due time. To probe a
session right away, say `$is-gpt-nerfed` in it.

The menu bar panel lists the sessions of the last 48 hours with their last verdict. Click a session for its report
(fingerprint, earlier probes, evidence) and right-click for actions. Each session has Probe and Retry, and the Fresh
session row probes a brand-new session to show what a new session gets right now.

From a terminal: `nerfed probe now` (pick a session), `nerfed report`, `nerfed explain <probe>`, `nerfed log --since 2h`.

Settings are in the app, or `nerfed config set <key> <value>`:

| key | default | |
| --- | --- | --- |
| `frequency` | `30m` | per session: every N minutes of activity (`30m`) or every N turns (`turns:8`) |
| `fresh_frequency` | `manual` | probe a brand-new session every N minutes, whatever you are doing |
| `served_check` | `true` | also ask the server which model it says answered, once per probe |
| `mode` | `auto` | `auto` probes in the background, `nudge` only reminds you |
| `halt_on_mismatch` | `false` | block tools after a mismatch until you say resume |
| `notify_on_ok`, `announce_ok` | `false` | also report Match |
| `hide_titles` | `false` | screenshot mode: neutral session names, no account |
| `check_updates` | `true` | ask GitHub for a newer release every 10 minutes |

## Accounts

Sessions are shared between Codex accounts, and a downgrade may be tied to the account rather than the session.
Every probe is therefore tagged with the signed-in account (a hash, never the id). After you switch accounts, older
verdicts show as "another account" and those sessions are probed again.

## Limits

- "The model you selected" is the model Codex asked for. If the server swaps the weights and keeps the name, only
  the fingerprint or a smaller context window can show it: the server's own answer names a model, and a name can be
  wrong.
- What the server names is not tied to the session you are working in. It answers for your account at that moment,
  which is why it can raise a verdict but never clear one.
- The bank is closed-set: a model outside it is mapped to its nearest look-alike. A name the server returns that
  Codex's catalog does not list is reported and counts for nothing.
- A probe costs three short answers on your account, plus one request that is closed before an answer is written.
  A fork that has not answered within five minutes is replaced once, so a slow model does not drop out of the sample.
- A model or effort change made through Codex's own settings is shown as a question ("was that you?"), because the
  plugin cannot tell whether you or Codex changed it.
- The probes run in a private app-server process that identifies itself as the client it checks for (the desktop app,
  or the CLI), because the service may route by client. Anything else that differs between the desktop's own
  connection and the probe's is invisible to it.

## Privacy

The plugin reads `~/.codex`: session records, the models cache, and `auth.json` for an account hash and a masked
e-mail. It writes to `~/.codex/is-gpt-nerfed` (probes, verdicts, `log.jsonl`). The forks are ordinary Codex
inference under your account.

Two requests leave your Mac, and both are switchable. The server check sends your Codex access token to Codex's own
backend, once per probe, the same place and the same credential Codex uses; it never reads the refresh token, and
the token goes nowhere else. Switch it off with `served_check` or in Settings. The app also asks GitHub for the
latest release tag every ten minutes while it is open (`check_updates`). Nothing else is sent anywhere, and your
records are never uploaded.

## Credits

[ModelTrace](https://github.com/xqy2006/ModelTrace) (xqy2006, MIT) for the fingerprint bank, scorer, prompts and the
fork-and-verify sequence; [hlwy-ai-checker](https://github.com/hanlinwenyuan/hlwy-ai-checker) for the random-number
idea; [simple-term-menu](https://github.com/IngoMeyer441/simple-term-menu) (MIT) for the session picker.

MIT license. Internals, build and contribution notes: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).
