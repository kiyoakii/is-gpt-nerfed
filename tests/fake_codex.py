#!/usr/bin/env python3
"""A fake `codex app-server --stdio` for offline tests.

Speaks just enough of the app-server JSON-RPC protocol for is-gpt-nerfed's probe runner. Behaviour is
controlled by environment variables:
  FAKE_CODEX_MODEL        model label whose reference text is returned (default gpt-6-astra)
  FAKE_CODEX_THREAD_MODEL model reported for the target thread (default = FAKE_CODEX_MODEL)
  FAKE_CODEX_THREAD_NO_MODEL=1  thread/read reports no model or provider for the thread (some Codex builds do that)
  FAKE_CODEX_PLUGIN_ID    pluginId hooks/list reports (default is-gpt-nerfed@is-gpt-nerfed)
  FAKE_CODEX_HOOK_WARNING a hook-loading warning hooks/list reports for that source
  FAKE_CODEX_TOOL=1       the probe "tries a tool" (item/started commandExecution) → must be rejected
  FAKE_CODEX_FAIL=1       the turn ends with status failed
  FAKE_CODEX_APPROVAL=1   the server sends an approval request during the turn
  FAKE_CODEX_FAIL_ONCE=p  exit before answering while file p exists (deleted on first hit): one transport failure
  FAKE_CODEX_BUSY_MODE    "fallback": newest turn is live (fork refused), the previous finished turn works
                          "wait": the only turn is live while FAKE_CODEX_BUSY_UNTIL exists; finished afterwards
  FAKE_CODEX_TRUST_FILE=p JSON file holding trusted hook hashes; enables hooks/list + config/batchWrite
  FAKE_CODEX_LOG=path     append every received message here
"""
import json
import os
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures", "reference_subset.jsonl")
HOOK_EVENTS = ["preToolUse", "sessionStart", "sessionEnd", "userPromptSubmit", "stop"]


def texts_for(model):
    out = []
    with open(FIXTURE, "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row["model_id"] == model:
                out.append(row["text"])
    return out or ["[1, 2, 3]"]


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def busy_now():
    mode = os.environ.get("FAKE_CODEX_BUSY_MODE")
    if mode == "fallback":
        return True
    if mode == "wait":
        p = os.environ.get("FAKE_CODEX_BUSY_UNTIL")
        return bool(p and os.path.exists(p))
    return False


def turns():
    mode = os.environ.get("FAKE_CODEX_BUSY_MODE")
    if mode == "fallback":
        return [{"id": "turn-live", "status": "completed"}, {"id": "turn-prev", "status": "completed"}]  # listed status lags: live turn shows as completed
    if mode == "wait":
        return [{"id": "turn-only", "status": "inProgress" if busy_now() else "completed"}]
    return [{"id": "turn-last", "status": "completed"}]


def trusted_hashes():
    p = os.environ.get("FAKE_CODEX_TRUST_FILE")
    if not p or not os.path.exists(p):
        return set()
    return set(json.load(open(p)))


def main():
    marker = os.environ.get("FAKE_CODEX_FAIL_ONCE")
    if marker and os.path.exists(marker):  # simulate one transport failure: die before answering anything
        os.remove(marker)
        sys.exit(1)
    model = os.environ.get("FAKE_CODEX_MODEL", "gpt-6-astra")
    thread_model = os.environ.get("FAKE_CODEX_THREAD_MODEL", model)
    originator = os.environ.get("CODEX_INTERNAL_ORIGINATOR_OVERRIDE") or "fake-client"  # what the real codex reports
    texts = texts_for(model)
    log = os.environ.get("FAKE_CODEX_LOG")
    forks = {}
    served = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if log:
            with open(log, "a") as f:
                f.write(line + "\n")
        method, rid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
        if method == "initialize":
            send({"id": rid, "result": {"userAgent": "fake-codex/0.0"}})
        elif method == "initialized":
            pass
        elif method == "thread/read":
            tid = params["threadId"]
            if tid.startswith("ephemeral-") or tid.startswith("side-"):
                send({"id": rid, "error": {"code": -32000, "message": f"no rollout found for thread {tid}"}})
            else:
                meta = {"id": tid, "path": f"/tmp/fake/{tid}.jsonl", "ephemeral": False, "model": thread_model,
                        "modelProvider": "openai", "reasoningEffort": "high", "cwd": "/tmp/fake-project",
                        "name": "fake thread", "originator": "Codex Desktop"}
                if os.environ.get("FAKE_CODEX_THREAD_NO_MODEL"):
                    meta.pop("model"), meta.pop("modelProvider")
                send({"id": rid, "result": {"thread": meta}})
        elif method == "thread/turns/list":
            send({"id": rid, "result": {"data": turns(), "nextCursor": None}})
        elif method == "thread/fork":
            once = os.environ.get("FAKE_CODEX_FORK_ERROR_ONCE")  # marker file: the next fork fails with a transient store error, once
            if once and os.path.exists(once):
                os.remove(once)
                send({"id": rid, "error": {"code": -32000, "message": "failed to prepare paginated fork: thread-store internal error: thread history projection for x is behind durable rollout"}})
                continue
            last = params.get("lastTurnId")
            if (os.environ.get("FAKE_CODEX_BUSY_MODE") == "fallback" and last == "turn-live") or \
                    (os.environ.get("FAKE_CODEX_BUSY_MODE") == "wait" and busy_now()):
                send({"id": rid, "error": {"code": -32000, "message": f"lastTurnId '{last}' identifies an in-progress turn"}})
                continue
            fid = "ephemeral-" + uuid.uuid4().hex[:8]
            forks[fid] = params
            send({"id": rid, "result": {"thread": {"id": fid, "ephemeral": True, "originator": originator, "forkedFromId": params["threadId"], "cwd": params.get("cwd"),
                                                   "model": params.get("model")},
                                        "model": params.get("model"), "modelProvider": params.get("modelProvider"),
                                        "reasoningEffort": (params.get("config") or {}).get("model_reasoning_effort"),
                                        "cwd": params.get("cwd"), "serviceTier": None}})
        elif method == "thread/start":  # a brand-new ephemeral session (the fresh probe)
            fid = "fresh-" + uuid.uuid4().hex[:8]
            forks[fid] = params
            send({"id": rid, "result": {"thread": {"id": fid, "ephemeral": bool(params.get("ephemeral", True)), "originator": originator,
                                                   "cwd": params.get("cwd"), "model": params.get("model")},
                                        "model": params.get("model"), "modelProvider": params.get("modelProvider"),
                                        "reasoningEffort": (params.get("config") or {}).get("model_reasoning_effort"),
                                        "cwd": params.get("cwd"), "serviceTier": None}})
        elif method == "turn/start":
            fid = params["threadId"]
            turn_id = "turn-" + uuid.uuid4().hex[:6]
            send({"id": rid, "result": {"turn": {"id": turn_id, "status": "inProgress"}}})
            send({"method": "turn/started", "params": {"threadId": fid, "turn": {"id": turn_id, "status": "inProgress"}}})
            hang = os.environ.get("FAKE_CODEX_HANG_ONCE")  # marker file: the next turn anywhere never answers (a stuck fork), once
            if hang and os.path.exists(hang):
                os.remove(hang)
                served += 1
                continue
            if os.environ.get("FAKE_CODEX_APPROVAL"):
                send({"id": 900 + served, "method": "item/commandExecution/requestApproval",
                      "params": {"threadId": fid, "turnId": turn_id, "command": "rm -rf /"}})
            if os.environ.get("FAKE_CODEX_TOOL"):
                send({"method": "item/started", "params": {"threadId": fid, "turnId": turn_id,
                                                           "item": {"id": "cmd-1", "type": "commandExecution", "command": "python3 -c 'import random'"}}})
            text = texts[served % len(texts)]
            served += 1
            send({"method": "item/started", "params": {"threadId": fid, "turnId": turn_id, "item": {"id": "msg-1", "type": "agentMessage", "text": ""}}})
            send({"method": "item/completed", "params": {"threadId": fid, "turnId": turn_id,
                                                         "item": {"id": "msg-1", "type": "agentMessage", "text": text, "phase": "final_answer"}}})
            send({"method": "thread/tokenUsage/updated", "params": {"threadId": fid, "turnId": turn_id,
                                                                    "tokenUsage": {"last": {"inputTokens": 12000, "cachedInputTokens": 11000, "outputTokens": 1300}}}})
            status = "failed" if os.environ.get("FAKE_CODEX_FAIL") else "completed"
            time.sleep(0.05)
            send({"method": "turn/completed", "params": {"threadId": fid, "turn": {"id": turn_id, "status": status}}})
        elif method == "turn/interrupt":
            send({"id": rid, "result": {}})
        elif method == "hooks/list" and os.environ.get("FAKE_CODEX_TRUST_FILE"):
            trusted = trusted_hashes()
            hooks = []
            for i, ev in enumerate(HOOK_EVENTS):
                h = f"sha256:fake-{ev}"
                hooks.append({"key": f"is-gpt-nerfed@is-gpt-nerfed:plugin.json#hooks[0]:{ev}:0:0", "eventName": ev, "handlerType": "command",
                              "command": f"nerfed hook --event {ev}", "source": "plugin",
                              "pluginId": os.environ.get("FAKE_CODEX_PLUGIN_ID", "is-gpt-nerfed@is-gpt-nerfed"),
                              "enabled": True, "currentHash": h, "trustStatus": "trusted" if h in trusted else "untrusted", "displayOrder": i})
            group = {"cwd": "/tmp/fake-project", "hooks": hooks, "errors": [],
                     "warnings": [w] if (w := os.environ.get("FAKE_CODEX_HOOK_WARNING")) else []}
            send({"id": rid, "result": {"data": [group]}})
        elif method == "config/batchWrite" and os.environ.get("FAKE_CODEX_TRUST_FILE"):
            trusted = trusted_hashes()
            for e in params.get("edits") or []:
                if e.get("keyPath", "").startswith("hooks.state.") and isinstance(e.get("value"), dict):
                    trusted.add(e["value"].get("trusted_hash"))
            with open(os.environ["FAKE_CODEX_TRUST_FILE"], "w") as f:
                json.dump(sorted(trusted), f)
            send({"id": rid, "result": {"status": "ok", "version": "sha256:fake", "filePath": "/tmp/fake-config.toml"}})
        elif rid is not None and method is None:
            pass  # reply to our own server request
        elif rid is not None:
            send({"id": rid, "error": {"code": -32601, "message": f"unsupported {method}"}})


if __name__ == "__main__":
    main()
