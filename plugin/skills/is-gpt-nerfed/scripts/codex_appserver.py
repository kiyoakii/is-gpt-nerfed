"""Minimal Codex app-server client used to run fingerprint probes in ephemeral forks.

A probe never touches the user's thread: we spawn our own `codex app-server --stdio`, read the target
thread's persisted settings, fork it `ephemeral: true` at its last completed turn (the same mechanism the
desktop's `/side` uses), start exactly one text-only turn per fork, collect the model's answer, and exit.
Ephemeral forks are never written to disk, so nothing appears in the Codex UI.

The fork-and-verify sequence follows ModelTrace Guard (MIT, xqy2006), which pioneered probing Codex threads
through native forks; see plugin/assets/modeltrace/provenance.json.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import threading
import time
import uuid

CLIENT_INFO = {"name": "is-gpt-nerfed", "version": "0.5.2"}
FINISHED_TURN = ("completed", "interrupted", "failed")
MESSAGE_ITEMS = ("userMessage", "agentMessage", "reasoning", "hookPrompt")

# Probe prompts adapted from ModelTrace Guard's prompts.mjs (MIT). The numerical task is what the
# fingerprint bank was enrolled with; keep it stable.
PROMPTS = {
    "zh": ("直接选择 {n} 个 1 到 355（含边界）的整数。允许重复；不要排序、平衡频数、修复重复，也不要刻意构造等差规律。",
           "直接回答一个 JSON 整数数组，不要解释。不要调用工具、读文件、运行代码或让其他模型代答；不要继续之前的任务。"),
    "en": ("Directly choose {n} integers from 1 through 355, inclusive. Allow repeats. Do not sort, balance frequencies, "
           "repair duplicates, or deliberately create an arithmetic pattern.",
           "Reply directly with one JSON integer array and no explanation. Do not call tools, read files, execute code or ask "
           "another model. Do not continue the preceding task."),
}
COUNT_RANGE = (292, 332)


class AppServerError(RuntimeError):
    pass


class ThreadBusy(AppServerError):
    """The session has a turn in progress, so Codex refuses to fork it right now."""


def fork_prompt(language: str, count: int) -> str:
    task, rules = PROMPTS.get(language) or PROMPTS["en"]
    return task.replace("{n}", str(count)) + "\n" + rules


class AppServer:
    """JSON-RPC-over-stdio client. Server-initiated requests (approvals, user input) are always refused."""

    def __init__(self, codex_bin: str, env: dict | None = None, hooks_enabled: bool = False, originator: str | None = None):
        environ = dict(os.environ if env is None else env)
        environ["NERFED_PROBE_PROCESS"] = "1"
        if originator:
            # The originator is the client name Codex reports to the service with every request (the desktop app says
            # "Codex Desktop"). A probe identifies itself as the client it checks for, in case routing depends on it;
            # without this, sessions started through the app-server carry the clientInfo name instead.
            environ["CODEX_INTERNAL_ORIGINATOR_OVERRIDE"] = originator
        # Our private app-server must not fire anyone's hooks or desktop notifications while it probes.
        # (`hooks_enabled` is only used to inspect/trust hook definitions; no turn ever runs in that mode.)
        args = [codex_bin, "app-server", "--stdio", "-c", "notify=[]"]
        if not hooks_enabled:
            args += ["-c", "features.hooks=false"]
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, env=environ, text=True, bufsize=1)
        self._write_lock = threading.Lock()
        self._cond = threading.Condition()
        self._next_id = 0
        self._pending: dict[int, dict] = {}
        self.notifications: list[dict] = []
        self.server_requests: list[dict] = []
        self.closed = False
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    # -- transport -------------------------------------------------------------------------------
    def _write(self, message: dict) -> None:
        data = json.dumps(message) + "\n"
        with self._write_lock:
            try:
                self.proc.stdin.write(data)
                self.proc.stdin.flush()
            except (BrokenPipeError, ValueError, OSError) as e:
                raise AppServerError(f"codex app-server transport closed: {e}") from e

    def _read_loop(self) -> None:
        try:
            for line in self.proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except Exception:
                    continue
                if not isinstance(message, dict):
                    continue
                if "method" in message and "id" in message:  # server → client request: refuse
                    try:
                        self._write({"id": message["id"], "error": {"code": -32601,
                                    "message": "is-gpt-nerfed probes do not execute tools or grant permissions"}})
                    except AppServerError:
                        pass
                    with self._cond:
                        self.server_requests.append(message)
                        self.notifications.append({"method": "_server_request", "params": {**(message.get("params") or {}),
                                                                                             "_request_method": message["method"]}})
                        self._cond.notify_all()
                elif "id" in message:
                    with self._cond:
                        entry = self._pending.pop(message["id"], None)
                        if entry is not None:
                            entry["result"], entry["error"], entry["done"] = message.get("result"), message.get("error"), True
                        self._cond.notify_all()
                else:
                    with self._cond:
                        self.notifications.append(message)
                        self._cond.notify_all()
        finally:
            with self._cond:
                self.closed = True
                self._cond.notify_all()

    def request(self, method: str, params: dict | None = None, timeout: float = 15.0):
        with self._cond:
            self._next_id += 1
            request_id = self._next_id
            entry = {"done": False, "result": None, "error": None, "method": method}
            self._pending[request_id] = entry
        self._write({"id": request_id, "method": method, "params": params or {}})
        deadline = time.time() + timeout
        with self._cond:
            while not entry["done"]:
                if self.closed:
                    raise AppServerError(f"codex app-server exited during {method}")
                remaining = deadline - time.time()
                if remaining <= 0:
                    self._pending.pop(request_id, None)
                    raise AppServerError(f"codex {method} timed out after {timeout:.0f}s")
                self._cond.wait(remaining)
        if entry["error"]:
            raise AppServerError(f"codex {method}: {(entry['error'] or {}).get('message') or entry['error']}")
        return entry["result"]

    def notify(self, method: str, params: dict | None = None) -> None:
        self._write({"method": method, "params": params or {}})

    def wait_for_notifications(self, seen: int, timeout: float) -> bool:
        with self._cond:
            if len(self.notifications) > seen or self.closed:
                return True
            self._cond.wait(timeout)
            return len(self.notifications) > seen or self.closed

    def initialize(self):
        result = self.request("initialize", {"clientInfo": CLIENT_INFO, "capabilities": {"experimentalApi": True}}, 20)
        self.notify("initialized")
        return result

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
                self.proc.wait(timeout=3)
            except Exception:
                pass


# -- thread helpers -----------------------------------------------------------------------------


def read_thread(app: AppServer, thread_id: str, hints: dict | None = None) -> dict:
    """Metadata for forking. Codex does not always report a model for a session (some builds leave the field out),
    so `hints` — what the caller's own record of the session says (model, effort, cwd) — fills the gaps. The fields
    that came from there travel with the thread as `hinted`, so a probe can say where its model came from."""
    thread = (app.request("thread/read", {"threadId": thread_id, "includeTurns": False}, 20) or {}).get("thread") or {}
    if thread.get("id") != thread_id:
        raise AppServerError("codex returned metadata for a different thread")
    if thread.get("ephemeral") or not isinstance(thread.get("path"), str) or not thread["path"]:
        raise AppServerError("session has no persisted history to fork (ephemeral or not saved yet)")
    thread = dict(thread)
    hinted = []
    for key, hint in (("model", (hints or {}).get("model")), ("reasoningEffort", (hints or {}).get("effort")),
                      ("cwd", (hints or {}).get("cwd"))):
        if not thread.get(key) and hint:
            thread[key] = hint
            hinted.append(key)
    if thread.get("model") and not thread.get("modelProvider"):
        thread["modelProvider"] = "openai"  # Codex's own default; only ever missing when it reports no model either
    if not thread.get("model"):
        raise AppServerError("neither Codex nor this session's record names a model for it")
    if not thread.get("cwd"):
        raise AppServerError("thread metadata lacks cwd")
    thread["hinted"] = hinted
    return thread


def list_turns(app: AppServer, thread_id: str, limit: int = 6) -> list[dict]:
    data = (app.request("thread/turns/list", {"threadId": thread_id, "limit": limit, "itemsView": "notLoaded",
                                              "sortDirection": "desc"}, 20) or {}).get("data") or []
    return [t for t in data if isinstance(t.get("id"), str)]


def finished_turns(app: AppServer, thread_id: str) -> list[dict]:
    """Newest first. The listed status can lag the live session (the desktop steers into running turns), so
    callers still have to handle a fork refusal with ThreadBusy."""
    turns = list_turns(app, thread_id)
    if not turns:
        raise AppServerError("session has no turns yet")
    return [t for t in turns if t.get("status") in FINISHED_TURN]


def last_turn(app: AppServer, thread_id: str) -> dict:
    done = finished_turns(app, thread_id)
    if not done:
        raise ThreadBusy("session has no finished turn yet; wait for the current turn to finish")
    return done[0]


def fork_at_latest_finished_turn(app: AppServer, thread: dict, on_wait=None, wait_until: float = 0.0) -> tuple[dict, dict]:
    """Fork the thread at its newest finished turn; if Codex refuses because that turn is still live, fall back
    to the previous finished turn, and if nothing is forkable wait (polling) until `wait_until`."""
    waited = False
    while True:
        candidates = finished_turns(app, thread["id"])
        last_error: AppServerError | None = None
        for cand in candidates[:3]:
            try:
                return cand, fork_ephemeral(app, thread, cand["id"])
            except ThreadBusy as e:
                last_error = e
        if not candidates:
            last_error = ThreadBusy("session has no finished turn yet")
        if time.time() >= wait_until:
            raise last_error or ThreadBusy("thread is busy")
        if not waited and on_wait:
            on_wait(str(last_error))
        waited = True
        time.sleep(min(10.0, max(1.0, wait_until - time.time())))


def fork_params(thread: dict, turn_id: str) -> dict:
    params = {"threadId": thread["id"], "lastTurnId": turn_id, "ephemeral": True, "excludeTurns": True,
              "model": thread["model"], "modelProvider": thread["modelProvider"], "cwd": thread["cwd"]}
    if thread.get("reasoningEffort"):
        params["config"] = {"model_reasoning_effort": thread["reasoningEffort"]}
    return params


def fork_ephemeral(app: AppServer, thread: dict, turn_id: str) -> dict:
    try:
        response = app.request("thread/fork", fork_params(thread, turn_id), 45) or {}
    except AppServerError as e:
        msg = str(e).lower()
        if "in-progress" in msg or "in progress" in msg or "inprogress" in msg:
            raise ThreadBusy(str(e)) from None
        raise
    fork = response.get("thread") or {}
    if not fork.get("ephemeral") or not fork.get("id") or fork.get("path") or fork["id"] == thread["id"] \
            or fork.get("forkedFromId") != thread["id"]:
        raise AppServerError("codex did not create an ephemeral fork of the target thread")
    if response.get("model") != thread["model"] or response.get("modelProvider") != thread["modelProvider"]:
        raise AppServerError(f"fork settings differ from the thread ({response.get('model')} vs {thread['model']})")
    if thread.get("reasoningEffort") and response.get("reasoningEffort") not in (None, thread["reasoningEffort"]):
        raise AppServerError("fork reasoning effort differs from the thread")
    return {"id": fork["id"], "model": response.get("model"), "provider": response.get("modelProvider"),
            "effort": response.get("reasoningEffort"), "cwd": response.get("cwd"), "service_tier": response.get("serviceTier")}


# -- probe runner -------------------------------------------------------------------------------


def rate_limit_summary(rl: dict) -> dict:
    """The usage snapshot Codex last reported (`account/rateLimits/updated`), kept for the record. Informational only:
    Codex parses one snapshot per limit family from the response headers and reports each in turn, so this is not
    necessarily the bucket the request was charged to, and it never identifies the model that answered.
    Accepts camelCase or snake_case."""
    if not isinstance(rl, dict):
        return {}
    def g(d, *names):
        for n in names:
            if isinstance(d, dict) and d.get(n) is not None:
                return d[n]
        return None
    primary = g(rl, "primary") or {}
    return {"limit_id": g(rl, "limitId", "limit_id"), "limit_name": g(rl, "limitName", "limit_name"),
            "used_percent": g(primary, "usedPercent", "used_percent"), "window_minutes": g(primary, "windowMinutes", "window_minutes")}


def run_turns(app: AppServer, forks: list[dict], deadline: float, parallel: bool = True) -> None:
    t_start = time.time()
    """Start one text-only turn per fork and collect the final agent message. Mutates each fork dict:
    text, error, usage, rate_limits, turn_id, elapsed_s."""
    states = {f["id"]: f for f in forks}
    app.last_rate_limits = getattr(app, "last_rate_limits", None)
    for f in forks:
        f.update({"text": None, "other": [], "done": False, "error": None, "usage": None, "rate_limits": None, "turn_id": None, "started_at": None})

    def start(f: dict) -> None:
        f["started_at"] = time.time()
        try:
            response = app.request("turn/start", {"threadId": f["id"], "input": [{"type": "text", "text": f["prompt"]}]},
                                   max(5.0, min(30.0, deadline - time.time())))
            f["turn_id"] = ((response or {}).get("turn") or {}).get("id")
        except AppServerError as e:
            f["error"], f["done"] = str(e), True

    def finish(f: dict, error: str | None = None) -> None:
        if f["done"]:
            return
        f["done"] = True
        f["elapsed_s"] = round(time.time() - (f["started_at"] or time.time()), 1)
        if error:
            f["error"] = error
        elif f["text"] is None:
            f["text"] = f["other"][0] if len(f["other"]) == 1 else ("\n".join(f["other"]) if f["other"] else None)
            if f["text"] is None:
                f["error"] = "probe did not return a final text answer"

    def handle(message: dict) -> None:
        method, params = message.get("method"), message.get("params") or {}
        if method == "account/rateLimits/updated":  # account-level usage snapshot, recorded with the probe
            app.last_rate_limits = rate_limit_summary(params.get("rateLimits") or params)
            for g in forks:
                if not g["done"]:
                    g["rate_limits"] = app.last_rate_limits
            return
        f = states.get(params.get("threadId"))
        if not f or f["done"]:
            return
        if method == "item/started":
            if (params.get("item") or {}).get("type") not in MESSAGE_ITEMS:
                finish(f, f"probe attempted a tool ({(params.get('item') or {}).get('type')}); no sample accepted")
        elif method == "item/completed":
            item = params.get("item") or {}
            if item.get("type") == "agentMessage":
                if item.get("phase") in ("final_answer", "final"):
                    f["text"] = item.get("text")
                elif not item.get("phase"):
                    f["other"].append(item.get("text") or "")
        elif method == "thread/tokenUsage/updated":
            last = (params.get("tokenUsage") or {}).get("last") or {}
            if last:
                f["usage"] = {"input": last.get("inputTokens"), "cached": last.get("cachedInputTokens"), "output": last.get("outputTokens")}
        elif method == "turn/completed":
            turn = params.get("turn") or {}
            if f["turn_id"] and turn.get("id") not in (None, f["turn_id"]):
                return
            finish(f, None if turn.get("status") == "completed" else f"probe turn ended with status {turn.get('status')}")
        elif method == "error":
            if not params.get("willRetry"):
                finish(f, f"probe inference failed: {(params.get('error') or {}).get('message') or params.get('message') or 'error'}")
        elif method == "_server_request":
            finish(f, f"probe requested {params.get('_request_method')}; refused, no sample accepted")

    pending = list(forks)
    if parallel:
        for f in pending:
            start(f)
        pending = []
    seen = 0
    while time.time() < deadline:
        if pending and all(f["done"] for f in forks if f not in pending):
            start(pending.pop(0))
        if all(f["done"] for f in forks):
            break
        app.wait_for_notifications(seen, 1.0)
        while seen < len(app.notifications):
            handle(app.notifications[seen])
            seen += 1
        if app.closed:
            for f in forks:
                finish(f, "codex app-server exited before the probe completed")
            break
    for f in forks:
        if not f["done"]:
            finish(f, f"fork timed out: no answer within {int(time.time() - t_start)} s")
            if f.get("turn_id"):
                try:
                    app.request("turn/interrupt", {"threadId": f["id"], "turnId": f["turn_id"]}, 3)
                except AppServerError:
                    pass
        f.pop("other", None)
        f.pop("started_at", None)


def probe_thread(codex_bin: str, thread_id: str, queries: int = 3, languages=("zh", "en"), timeout_s: float = 180,
                 parallel: bool = True, rng: random.Random | None = None, busy_wait_s: float = 0.0, on_wait=None,
                 originator: str | None = None, hints: dict | None = None) -> dict:
    """Fork `thread_id` `queries` times (same finished turn), ask each fork for a number sequence, return the answers.
    A thread with a live turn is forked at its previous finished turn; if none is forkable, wait up to `busy_wait_s`."""
    rng = rng or random.Random()
    t0 = time.time()
    app = AppServer(codex_bin, originator=originator)
    try:
        app.initialize()
        thread = read_thread(app, thread_id, hints)
        turn, first = fork_at_latest_finished_turn(app, thread, on_wait=on_wait, wait_until=t0 + busy_wait_s)
        deadline = time.time() + timeout_s
        forks = [first]
        for _ in range(max(1, int(queries)) - 1):
            forks.append(fork_ephemeral(app, thread, turn["id"]))
        for fork in forks:
            fork["language"] = rng.choice(list(languages) or ["en"])
            fork["count"] = rng.randint(*COUNT_RANGE)
            fork["prompt"] = fork_prompt(fork["language"], fork["count"])
        run_turns(app, forks, deadline, parallel=parallel)
    finally:
        app.close()
    return {
        "originator": originator,
        "thread": {"id": thread["id"], "model": thread.get("model"), "provider": thread.get("modelProvider"),
                   "hinted": thread.get("hinted") or [],
                   "effort": thread.get("reasoningEffort"), "cwd": thread.get("cwd"), "path": thread.get("path"),
                   "originator": thread.get("originator"),
                   "name": thread.get("name"), "last_turn": turn["id"], "last_turn_status": turn.get("status")},
        "forks": [{k: v for k, v in f.items() if k != "prompt"} for f in forks],
        "elapsed_s": round(time.time() - t0, 1), "parallel": parallel,
        "server_requests": len(app.server_requests), "rate_limits": getattr(app, "last_rate_limits", None),
    }


# -- hooks (inspection and trust, the same calls the Codex TUI's /hooks screen makes) --------------


def hook_belongs_to(hook: dict, plugin_name: str) -> bool:
    """Codex names a hook's plugin `<plugin>@<marketplace>`, and the marketplace is whatever the user installed
    from, so only the plugin part is ours to match. The file a hook came from catches any other shape."""
    pid = str(hook.get("pluginId") or "")
    if pid == plugin_name or pid.startswith(plugin_name + "@"):
        return True
    return f"/{plugin_name}/" in str(hook.get("sourcePath") or "") or f"/{plugin_name}/scripts/" in str(hook.get("command") or "")


def list_plugin_hooks(codex_bin: str, plugin_name: str) -> dict:
    """{"hooks": [...], "notes": [...]}: the plugin's hooks as Codex lists them, plus what its loader said about the
    source they came from (that group's `errors` and `warnings`, which Codex's hooks screen shows as loading problems)."""
    app = AppServer(codex_bin, hooks_enabled=True)
    try:
        app.initialize()
        data = (app.request("hooks/list", {}, 30) or {}).get("data") or []
    finally:
        app.close()
    hooks, notes = [], []
    for group in data:
        mine = [h for h in (group.get("hooks") or []) if hook_belongs_to(h, plugin_name)]
        hooks.extend(mine)
        for kind in ("errors", "warnings"):
            for message in group.get(kind) or []:
                if mine or plugin_name in str(message):  # complaints about our source, not about someone else's
                    notes.append({"kind": kind[:-1], "message": str(message)[:300]})
    return {"hooks": hooks, "notes": notes}


def trust_hooks(codex_bin: str, hooks: list[dict]) -> dict:
    """Record trust for the given hook definitions (their current hashes) in the user's config.toml."""
    edits = [{"keyPath": 'hooks.state."' + h["key"].replace('"', '\\"') + '"', "mergeStrategy": "upsert",
              "value": {"enabled": True, "trusted_hash": h["currentHash"]}} for h in hooks if h.get("key") and h.get("currentHash")]
    if not edits:
        return {"status": "nothing to do"}
    app = AppServer(codex_bin, hooks_enabled=True)
    try:
        app.initialize()
        return app.request("config/batchWrite", {"edits": edits, "reloadUserConfig": True}, 30) or {}
    finally:
        app.close()


def start_ephemeral(app: AppServer, model: str, effort: str | None, provider: str | None, cwd: str) -> dict:
    """Start a brand-new ephemeral thread (no history) with the given model settings."""
    params = {"ephemeral": True, "model": model, "cwd": cwd}
    if provider:
        params["modelProvider"] = provider
    if effort:
        params["config"] = {"model_reasoning_effort": effort}
    response = app.request("thread/start", params, 45) or {}
    thread = response.get("thread") or {}
    if not thread.get("id") or not thread.get("ephemeral", True):
        raise AppServerError("codex did not create an ephemeral thread")
    if response.get("model") and response.get("model") != model:
        raise AppServerError(f"fresh thread model differs from the request ({response.get('model')} vs {model})")
    return {"id": thread["id"], "model": response.get("model") or model, "provider": response.get("modelProvider") or provider,
            "effort": response.get("reasoningEffort") or effort, "cwd": response.get("cwd") or cwd,
            "service_tier": response.get("serviceTier"), "originator": thread.get("originator")}


def probe_fresh(codex_bin: str, model: str, effort: str | None = None, provider: str | None = "openai", cwd: str | None = None,
                queries: int = 3, languages=("zh", "en"), timeout_s: float = 180, parallel: bool = True,
                rng: random.Random | None = None, originator: str | None = None) -> dict:
    """Global probe: `queries` brand-new ephemeral sessions (no conversation context), one text-only turn each."""
    rng = rng or random.Random()
    cwd = cwd or os.path.expanduser("~")
    t0 = time.time()
    deadline = t0 + timeout_s
    app = AppServer(codex_bin, originator=originator)
    try:
        app.initialize()
        forks = []
        for _ in range(max(1, int(queries))):
            fork = start_ephemeral(app, model, effort, provider, cwd)
            fork["language"] = rng.choice(list(languages) or ["en"])
            fork["count"] = rng.randint(*COUNT_RANGE)
            fork["prompt"] = fork_prompt(fork["language"], fork["count"])
            forks.append(fork)
        run_turns(app, forks, deadline, parallel=parallel)
    finally:
        app.close()
    return {
        "originator": originator,
        "thread": {"id": None, "model": forks[0]["model"] if forks else model, "provider": provider, "effort": forks[0].get("effort") if forks else effort,
                   "cwd": cwd, "path": None, "name": "fresh session", "last_turn": None},
        "forks": [{k: v for k, v in f.items() if k != "prompt"} for f in forks],
        "elapsed_s": round(time.time() - t0, 1), "parallel": parallel, "server_requests": len(app.server_requests),
        "rate_limits": getattr(app, "last_rate_limits", None),
    }


def fork_doctor(codex_bin: str, thread_id: str) -> dict:
    """Prove that an ephemeral fork of the thread can be created, without starting any model turn."""
    t0 = time.time()
    app = AppServer(codex_bin)
    try:
        app.initialize()
        thread = read_thread(app, thread_id)
        turn = last_turn(app, thread_id)
        fork = fork_ephemeral(app, thread, turn["id"])
    finally:
        app.close()
    return {"ok": True, "thread": thread_id, "model": thread.get("model"), "effort": thread.get("reasoningEffort"),
            "provider": thread.get("modelProvider"), "cwd": thread.get("cwd"), "last_turn": turn["id"],
            "fork_id": fork["id"], "elapsed_s": round(time.time() - t0, 1), "inference_requests": 0}


def new_probe_id() -> str:
    return uuid.uuid4().hex[:10]
