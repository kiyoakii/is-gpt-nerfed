"""Unit + offline end-to-end tests for the dgc CLI. Run: python3 -m unittest discover -s tests -v"""
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="dgc-test-")
os.environ["NERFED_HOME"] = os.path.join(TMP, "ledger")
os.environ["NERFED_NO_UPDATE_CHECK"] = "1"  # tests never touch the network
os.environ["CODEX_HOME"] = os.path.join(TMP, "codex-home")
os.makedirs(os.environ["CODEX_HOME"], exist_ok=True)
for var in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_SANDBOX_NETWORK_DISABLED", "NERFED_PROBE_PROCESS"):
    os.environ.pop(var, None)

DGC_PATH = os.path.join(ROOT, "plugin", "skills", "is-gpt-nerfed", "scripts", "nerfed")
FAKE_CODEX = os.path.join(ROOT, "tests", "fake_codex.py")
loader = importlib.machinery.SourceFileLoader("dgc", DGC_PATH)
spec = importlib.util.spec_from_loader("dgc", loader)
dgc = importlib.util.module_from_spec(spec)
loader.exec_module(dgc)
dgc.responses_meta.RESPONSES_URL = "http://127.0.0.1:9/no-network-in-tests"  # the server check never reaches chatgpt.com here


def rollout_lines(*records):
    return "".join(json.dumps(r) + "\n" for r in records)


def turn(tid, model, effort):
    return {"type": "turn_context", "timestamp": f"t{tid}", "payload": {"turn_id": str(tid), "model": model,
            "collaboration_mode": {"settings": {"reasoning_effort": effort}}}}


def settings(model, effort, tier=None):
    s = {"model": model, "reasoning_effort": effort}
    if tier:
        s["service_tier"] = tier
    return {"type": "event_msg", "timestamp": "ts", "payload": {"type": "thread_settings_applied", "thread_settings": s}}


def tokens(ctx):
    return {"type": "event_msg", "payload": {"type": "token_count", "info": {"model_context_window": ctx}}}


def run_cli(argv, env=None):
    buf = io.StringIO()
    with mock.patch.dict(os.environ, env or {}):
        with redirect_stdout(buf):
            try:
                rc = dgc.main(argv)
            except SystemExit as e:
                rc = e.code
    return rc, buf.getvalue()


def run_hook(payload):
    with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
            mock.patch.object(sys.stdin, "isatty", return_value=False, create=True):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = dgc.main(["hook"])
    assert rc == 0
    return buf.getvalue()


def fixture_rows():
    with open(os.path.join(ROOT, "tests", "fixtures", "reference_subset.jsonl")) as f:
        return [json.loads(l) for l in f if l.strip()]


class ScannerTests(unittest.TestCase):
    def write(self, text):
        p = os.path.join(TMP, f"rollout-{os.urandom(3).hex()}.jsonl")
        with open(p, "w") as f:
            f.write(text)
        return p

    def test_silent_downgrade_is_hard_evidence(self):
        p = self.write(rollout_lines(turn(1, "gpt-6-astra", "max"), tokens(258400), turn(2, "gpt-reserve", "medium"), tokens(128000)))
        scan, ev = dgc.scan_full(p, frozenset({"gpt-reserve"}))
        sev = {e["kind"]: e["severity"] for e in ev}
        self.assertEqual(sev, {"silent_model_change": "hard", "silent_effort_change": "hard", "hidden_model": "hard", "context_window_change": "hard"})
        self.assertEqual(scan["models_seen"], {"gpt-6-astra": 1, "gpt-reserve": 1})

    def test_settings_applied_change_is_soft_or_good(self):
        p = self.write(rollout_lines(settings("gpt-6-astra", "max", "priority"), turn(1, "gpt-6-astra", "max"),
                                     settings("gpt-5.5", "high", "default"), turn(2, "gpt-5.5", "high"),
                                     settings("gpt-6-astra", "max", "default"), turn(3, "gpt-6-astra", "max")))
        _, ev = dgc.scan_full(p, frozenset())
        kinds = {(e["kind"], e["severity"]) for e in ev}
        self.assertIn(("applied_model_change", "soft"), kinds, "gpt-6-astra → gpt-5.5 through settings: a downgrade, was that you?")
        self.assertIn(("applied_model_change", "good"), kinds, "back to gpt-6-astra: a newer generation, good news")
        self.assertIn(("service_tier_change", "info"), kinds)
        self.assertFalse(any(k == "silent_model_change" for k, _ in kinds))

    def test_reverted_changes_stop_being_active_and_usage_limit_is_labelled(self):
        def tokens_with_usage(ctx, pct):
            return {"type": "event_msg", "payload": {"type": "token_count", "info": {"model_context_window": ctx},
                                                     "rate_limits": {"primary": {"used_percent": pct}}}}
        p = self.write(rollout_lines(
            turn(1, "gpt-6-astra", "max"), tokens_with_usage(258400, 40),
            tokens_with_usage(258400, 98), settings("gpt-6-astra", "medium"), turn(2, "gpt-6-astra", "medium"),   # Codex at the limit
            tokens_with_usage(258400, 12), settings("gpt-6-astra", "high"), turn(3, "gpt-6-astra", "high")))     # switched back
        _, ev = dgc.scan_full(p, frozenset())
        kinds = [(e["kind"], e["severity"]) for e in ev]
        self.assertEqual(kinds, [("applied_effort_change", "soft"), ("applied_effort_change", "info")])
        self.assertEqual(dgc.compact_evidence(ev[0]), "Codex switched effort max → medium at the usage limit (98%)")
        self.assertEqual(dgc.active_evidence(ev), [], "the later switch back to high resolves the finding")
        # a plain settings change (not at the limit) keeps asking
        q = self.write(rollout_lines(turn(1, "gpt-6-astra", "high"), settings("gpt-6-astra", "low"), turn(2, "gpt-6-astra", "low")))
        _, ev2 = dgc.scan_full(q, frozenset())
        self.assertEqual(dgc.compact_evidence(ev2[0]), "Settings: effort high → low · was that you?")
        self.assertEqual(len(dgc.active_evidence(ev2)), 1)
        # the same transition on another day is recorded again (dedupe is per timestamp)
        r = self.write(rollout_lines(turn(1, "gpt-6-astra", "high"), settings("gpt-6-astra", "low"), turn(2, "gpt-6-astra", "low"),
                                     settings("gpt-6-astra", "high"), turn(3, "gpt-6-astra", "high"),
                                     settings("gpt-6-astra", "low"), turn(4, "gpt-6-astra", "low")))
        _, ev3 = dgc.scan_full(r, frozenset())
        self.assertEqual([e["severity"] for e in ev3], ["soft", "info", "soft"])
        self.assertEqual(len(dgc.active_evidence(ev3)), 1)

    def test_incremental_scan_and_partial_lines(self):
        p = self.write(rollout_lines(turn(1, "gpt-6-astra", "max")))
        scan = dgc.new_scan_state()
        self.assertEqual(dgc.scan_rollout(p, scan, frozenset()), [])
        with open(p, "a") as f:
            f.write('{"type": "turn_context", "payload": {"turn_id": "2", "model": "gpt-5.3-codex-spark"')
        self.assertEqual(dgc.scan_rollout(p, scan, frozenset()), [])
        with open(p, "a") as f:
            f.write("}}\n")
        ev = dgc.scan_rollout(p, scan, frozenset())
        self.assertEqual([(e["kind"], e["severity"]) for e in ev], [("silent_model_change", "hard")])
        self.assertEqual(dgc.scan_rollout(p, scan, frozenset()), [])

    def test_silent_upgrade_is_good_news(self):
        p = self.write(rollout_lines(turn(1, "gpt-5.6-sol", "high"), turn(2, "gpt-6-sol", "high")))
        _, ev = dgc.scan_full(p, frozenset())
        self.assertEqual([(e["kind"], e["severity"]) for e in ev], [("silent_model_change", "good")])
        self.assertEqual(dgc.compact_evidence(ev[0]), "Upgraded: gpt-5.6-sol → gpt-6-sol")
        self.assertIn("newer generation", ev[0].get("why", ""))
        self.assertEqual(len(dgc.active_evidence(ev)), 1, "good news stays active like any other finding")


class LogicTests(unittest.TestCase):
    def test_compare_models_orders_by_catalog_generation_size_then_ranking(self):
        levels_all = ["low", "medium", "high", "xhigh", "max", "ultra"]
        cat = {"gpt-6-astra": {"priority": 1, "visibility": "list", "supported_reasoning_levels": levels_all, "context_window": 272000},
               "gpt-5.6-sol": {"priority": 4, "visibility": "list", "supported_reasoning_levels": levels_all, "context_window": 272000, "upgrade": "gpt-6-sol"},
               "gpt-5.6-luna": {"priority": 8, "visibility": "list", "supported_reasoning_levels": levels_all[:-1], "context_window": 272000},
               "gpt-reserve": {"priority": 3, "visibility": "hide", "supported_reasoning_levels": levels_all[:3], "context_window": 272000}}
        c = lambda a, b: dgc.compare_models(a, b, cat)
        r = c("gpt-5.6-sol", "gpt-6-sol")
        self.assertEqual((r["direction"], r["confidence"]), ("upgrade", "high"))
        self.assertIn("successor", r["reason"])
        self.assertEqual(c("gpt-6-astra", "gpt-5.6-luna")["direction"], "downgrade")
        r = c("gpt-5.3-codex", "gpt-5.3-codex-spark")
        self.assertEqual((r["direction"], r["confidence"], r["reason"]), ("downgrade", "high", "smaller size tier"))
        self.assertEqual(c("gpt-6-astra", "gpt-reserve")["direction"], "downgrade")
        r = c("gpt-5.6-sol", "gpt-5.6-luna")
        self.assertEqual((r["direction"], r["confidence"]), ("downgrade", "medium"), "same generation and size: Codex's own ranking decides")
        self.assertEqual(c("gpt-5.6-luna", "gpt-5.6-sol")["direction"], "upgrade")
        self.assertEqual(c("gpt-6-astra", "gpt-6-astra")["direction"], "lateral")
        r = c("gpt-6-alpha", "gpt-6-beta")
        self.assertEqual((r["direction"], r["confidence"]), ("lateral", "low"), "unknown peers are not called either way")
        self.assertEqual(c("claude-opus-4-7", "claude-opus-4-8")["direction"], "upgrade")
        self.assertEqual(c("gpt-5.6-sol", "gpt-6-sol-spark")["confidence"], "medium", "newer but smaller: only a medium call")
        self.assertEqual(dgc.model_version("claude-haiku-4-5-20251001"), (4, 5))
        self.assertIsNone(dgc.model_version("codex-auto-review"))

    def test_ranking_and_frequency(self):
        self.assertGreater(dgc.model_rank("gpt-6-astra"), dgc.model_rank("gpt-5.6-sol"))
        self.assertEqual(dgc.classify_change("gpt-6-astra", "gpt-reserve"), "downgrade")
        self.assertEqual(dgc.classify_change("gpt-5.6-sol", "gpt-5.6-luna", {}), "lateral", "without a catalog the two are peers")
        self.assertEqual(dgc.parse_frequency("every 5 turns"), ("turns", 5))
        self.assertEqual(dgc.parse_frequency("2h"), ("minutes", 120))
        with self.assertRaises(ValueError):
            dgc.parse_frequency("sometimes")
        self.assertEqual(dgc.coerce_config_value("languages", "zh, en"), ["zh", "en"])
        with self.assertRaises(ValueError):
            dgc.coerce_config_value("languages", "klingon")

    @staticmethod
    def analysis(*rows):
        results = [{"model": m, "probability": p, "score": s} for m, p, s in rows]
        results.sort(key=lambda r: -r["probability"])
        return {"prediction": results[0]["model"], "probability": results[0]["probability"], "used_outputs": 3, "results": results}

    def test_verdicts(self):
        confident = self.analysis(("gpt-5.6-luna", 0.91, 1.8), ("gpt-6-astra", 0.03, 0.4), ("gpt-5.5", 0.06, 0.6))
        self.assertEqual(dgc.fingerprint_verdict("gpt-6-astra", confident, []), ("MISMATCH", "downgrade"))
        self.assertEqual(dgc.fingerprint_verdict("gpt-5.5", confident, []), ("MISMATCH", "upgrade"))
        self.assertEqual(dgc.fingerprint_verdict("openai/gpt-5.6-luna", confident, []), ("MATCH", None))
        self.assertEqual(dgc.fingerprint_verdict("gpt-7-nova", confident, []), ("UNLISTED", None))
        self.assertEqual(dgc.fingerprint_verdict(None, confident, []), ("UNKNOWN", None))
        self.assertEqual(dgc.fingerprint_verdict("gpt-6-astra", None, []), ("INVALID", None))
        self.assertEqual(dgc.fingerprint_verdict("gpt-6-astra", confident, [{"detail": "x"}]), ("DOWNGRADED!", "hard"))

    def test_confidence_gate(self):
        # top candidate wins but not confidently: SUSPICIOUS, never MISMATCH
        thin = self.analysis(("gpt-5.6-sol", 0.62, 1.1), ("gpt-6-astra", 0.31, 0.9), ("gpt-5.5", 0.07, 0.2))
        a = dgc.assess("gpt-6-astra", thin, [])
        self.assertEqual((a["verdict"], a["direction"], a["confidence"]), ("SUSPICIOUS", "downgrade", "low"))
        self.assertAlmostEqual(a["p_expected"], 0.31)
        self.assertAlmostEqual(a["margin"], 0.2)
        # a peaked softmax with a thin z-score margin is still SUSPICIOUS
        peaked = self.analysis(("gpt-5.6-sol", 0.95, 1.30), ("gpt-6-astra", 0.04, 1.05), ("gpt-5.5", 0.01, 0.1))
        self.assertEqual(dgc.assess("gpt-6-astra", peaked, [])["verdict"], "SUSPICIOUS")
        # p(top) high, p(declared) still too high
        split = self.analysis(("gpt-5.6-sol", 0.80, 1.5), ("gpt-6-astra", 0.20, 0.6), ("gpt-5.5", 0.0, 0.0))
        self.assertEqual(dgc.assess("gpt-6-astra", split, [])["verdict"], "MISMATCH")
        self.assertEqual(dgc.assess("gpt-6-astra", split, [], {"mismatch_confidence": 0.9})["verdict"], "SUSPICIOUS")
        # a weak MATCH is still a MATCH, flagged low confidence
        weak = self.analysis(("gpt-6-astra", 0.55, 1.0), ("gpt-5.6-sol", 0.45, 0.9))
        a = dgc.assess("gpt-6-astra", weak, [])
        self.assertEqual((a["verdict"], a["confidence"]), ("MATCH", "low"))
        self.assertFalse(dgc.needs_confirmation("gpt-6-astra", [], {"confirm_uncertain": True}))

    def test_probe_due(self):
        st = dgc.new_session("s")
        st["kind"], st["turns"] = "main", 7
        cfg = {"frequency": "turns:8", "nudge_cooldown_turns": 4}
        self.assertFalse(dgc.probe_due(st, cfg))
        st["turns"] = 8
        self.assertTrue(dgc.probe_due(st, cfg))
        st["last_probe_turn"] = 8
        self.assertFalse(dgc.probe_due(st, cfg))
        self.assertFalse(dgc.probe_due(st, {"frequency": "manual"}))
        st["created_ts"] = dgc.now() - 3600
        self.assertTrue(dgc.probe_due(st, {"frequency": "30m"}))


class ForkProbeTests(unittest.TestCase):
    """Drive the real probe runner against the fake app-server."""

    def setUp(self):
        dgc.ensure_dirs()
        dgc.save_config({**dgc.DEFAULT_CONFIG, "codex_bin": FAKE_CODEX, "notify": False, "sound": False, "probe_timeout_s": 30})
        dgc._BANK = None

    def test_match(self):
        rc, out = run_cli(["probe", "now", "--mode", "fork", "--thread", "main-thread-1"], {"FAKE_CODEX_MODEL": "gpt-6-astra"})
        self.assertEqual(rc, 0, out)
        self.assertIn("verdict: MATCH", out)
        self.assertIn("3/3 answers used", out)
        rec = dgc.read_json(dgc.probe_path(out.split("probe ")[1].split()[0]))
        self.assertEqual(rec["expected"], "gpt-6-astra")
        self.assertEqual(rec["prediction"], "gpt-6-astra")
        self.assertEqual(len(rec["forks"]), 3)
        self.assertTrue(all(f["usage"]["cached"] == 11000 for f in rec["forks"]))
        st = dgc.load_session("main-thread-1")
        self.assertEqual(st["alerts"], [], "MATCH is silent in the thread by default")
        self.assertIsNone(st["probe_running"])

    def test_mismatch_is_a_downgrade_with_alert_and_optional_halt(self):
        dgc.save_config({**dgc.load_config(), "halt_on_mismatch": True})
        rc, out = run_cli(["probe", "now", "--mode", "fork", "--thread", "main-thread-2"], {"FAKE_CODEX_MODEL": "gpt-5.5", "FAKE_CODEX_THREAD_MODEL": "gpt-6-astra"})
        self.assertEqual(rc, 0, out)
        self.assertIn("verdict: MISMATCH", out)
        self.assertIn("direction: downgrade", out)
        st = dgc.load_session("main-thread-2")
        self.assertEqual(len(st["alerts"]), 1)
        self.assertIsNotNone(st["halt"])
        # the halt denies work tools but lets dgc commands through; resume clears it
        base = {"session_id": "main-thread-2", "cwd": TMP, "model": "gpt-6-astra"}
        denied = json.loads(run_hook({**base, "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "npm test"}}))
        self.assertEqual(denied["decision"], "deny")
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        # the alert is handed to the model on the next model-visible hook, exactly once
        out = json.loads(run_hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "hi"}))
        self.assertIn("tell the user", out["hookSpecificOutput"]["additionalContext"].lower())
        self.assertIn("Congrats", out["systemMessage"])
        self.assertEqual(run_hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "again"}).strip(), "")
        # dgc's own commands pass through the halt; resume clears it
        allowed = run_hook({**base, "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": f"{DGC_PATH} resume --thread main-thread-2"}})
        self.assertNotIn('"deny"', allowed)
        run_cli(["resume", "--thread", "main-thread-2"])
        self.assertIsNone(dgc.load_session("main-thread-2")["halt"])

    def test_tool_attempt_and_failed_turn_are_invalid(self):
        rc, out = run_cli(["probe", "now", "--mode", "fork", "--thread", "main-thread-3"], {"FAKE_CODEX_TOOL": "1"})
        self.assertIn("verdict: INVALID", out)
        self.assertIn("attempted a tool", out)
        rc, out = run_cli(["probe", "now", "--mode", "fork", "--thread", "main-thread-3"], {"FAKE_CODEX_FAIL": "1"})
        self.assertIn("verdict: INVALID", out)
        rc, out = run_cli(["probe", "now", "--mode", "fork", "--thread", "main-thread-3"], {"FAKE_CODEX_APPROVAL": "1"})
        self.assertIn("verdict: INVALID", out)
        self.assertIn("refused", out)

    def test_transport_failure_is_retried_once(self):
        marker = os.path.join(TMP, "fail-once")
        open(marker, "w").close()
        rc, out = run_cli(["probe", "now", "--mode", "fork", "--thread", "main-thread-9"],
                          {"FAKE_CODEX_MODEL": "gpt-6-astra", "FAKE_CODEX_FAIL_ONCE": marker})
        self.assertIn("verdict: MATCH", out)
        self.assertIn("retried ×1", out)
        self.assertFalse(os.path.exists(marker))
        rec = dgc.read_json(dgc.probe_path(out.split("probe ")[1].split()[0]))
        self.assertEqual(rec["retries"], 1)
        self.assertEqual(rec["rounds"], 1)

    def test_suspicious_first_round_gets_a_confirmation_round(self):
        calls = {"n": 0}
        real = dgc.needs_confirmation

        def once(expected, outputs, cfg):
            calls["n"] += 1
            return calls["n"] == 1 or real(expected, outputs, cfg)

        with mock.patch.object(dgc, "needs_confirmation", side_effect=once):
            rc, out = run_cli(["probe", "now", "--mode", "fork", "--thread", "main-thread-10"], {"FAKE_CODEX_MODEL": "gpt-6-astra"})
        self.assertIn("6/6 answers used in 2 rounds", out)
        rec = dgc.read_json(dgc.probe_path(out.split("probe ")[1].split()[0]))
        self.assertEqual(rec["rounds"], 2)
        self.assertEqual(len(rec["forks"]), 6)
        self.assertEqual(rec["verdict"], "MATCH")

    def test_live_turn_falls_back_to_previous_finished_turn(self):
        rc, out = run_cli(["probe", "now", "--mode", "fork", "--thread", "busy-thread-1"],
                          {"FAKE_CODEX_MODEL": "gpt-6-astra", "FAKE_CODEX_BUSY_MODE": "fallback"})
        self.assertIn("verdict: MATCH", out)
        rec = dgc.read_json(dgc.probe_path(out.split("probe ")[1].split()[0]))
        self.assertEqual(rec["thread"]["last_turn"], "turn-prev")
        self.assertFalse(rec.get("waited_for_turn"))

    def test_live_turn_is_waited_for(self):
        import threading
        marker = os.path.join(TMP, "busy-until")
        open(marker, "w").close()
        dgc.save_config({**dgc.load_config(), "busy_wait_s": 30})
        threading.Timer(2.5, lambda: os.remove(marker)).start()
        rc, out = run_cli(["probe", "now", "--mode", "fork", "--thread", "busy-thread-2"],
                          {"FAKE_CODEX_MODEL": "gpt-6-astra", "FAKE_CODEX_BUSY_MODE": "wait", "FAKE_CODEX_BUSY_UNTIL": marker})
        self.assertIn("verdict: MATCH", out)
        rec = dgc.read_json(dgc.probe_path(out.split("probe ")[1].split()[0]))
        self.assertTrue(rec.get("waited_for_turn"))
        self.assertEqual(rec["thread"]["last_turn"], "turn-only")
        rc, log = run_cli(["log", "--probe", rec["id"], "--json"])
        kinds = [json.loads(l)["kind"] for l in log.splitlines() if l.strip()]
        self.assertEqual(kinds[0], "probe_start")
        self.assertIn("probe_wait", kinds)
        self.assertIn("probe_round", kinds)
        self.assertEqual(kinds[-1], "probe_verdict")
        dgc.save_config({**dgc.load_config(), "busy_wait_s": 600})

    def test_live_turn_gives_up_after_busy_wait(self):
        marker = os.path.join(TMP, "busy-forever")
        open(marker, "w").close()
        dgc.save_config({**dgc.load_config(), "busy_wait_s": 1})
        rc, out = run_cli(["probe", "now", "--mode", "fork", "--thread", "busy-thread-3"],
                          {"FAKE_CODEX_MODEL": "gpt-6-astra", "FAKE_CODEX_BUSY_MODE": "wait", "FAKE_CODEX_BUSY_UNTIL": marker})
        self.assertIn("verdict: INVALID", out)
        self.assertIn("stayed busy", out)
        snap = json.loads(run_cli(["snapshot", "--json"])[1])
        p = next(p for p in snap["recent_probes"] if p["thread_id"] == "busy-thread-3")
        self.assertTrue(p["retryable"], "a busy thread must offer Retry in the panel")
        os.remove(marker)
        dgc.save_config({**dgc.load_config(), "busy_wait_s": 600})

    def test_hooks_status_and_trust(self):
        trust_file = os.path.join(TMP, "trusted-hooks.json")
        env = {"FAKE_CODEX_TRUST_FILE": trust_file}
        rc, out = run_cli(["hooks", "status"], env)
        self.assertEqual(rc, 1)
        self.assertIn("0/5 hooks trusted", out)
        rc, out = run_cli(["hooks", "trust"], env)
        self.assertEqual(rc, 0)
        self.assertIn("trusted 5 hook(s)", out)
        self.assertIn("5/5 hooks trusted", out)
        self.assertEqual(len(json.load(open(trust_file))), 5)
        snap = json.loads(run_cli(["snapshot", "--json"], env)[1])
        self.assertEqual(snap["hooks"]["state"], "trusted")
        self.assertEqual(snap["hooks"]["trusted"], 5)
        rc, out = run_cli(["log", "--kind", "hooks_trust"])
        self.assertIn("hooks_trust", out)
        os.remove(dgc.HOOKS_STATUS_PATH)

    def test_unlisted_expected_model(self):
        rc, out = run_cli(["probe", "now", "--mode", "fork", "--thread", "main-thread-4"], {"FAKE_CODEX_MODEL": "gpt-6-astra", "FAKE_CODEX_THREAD_MODEL": "gpt-7-nova"})
        self.assertIn("verdict: UNLISTED", out)

    def test_sandbox_queues_and_stop_hook_spawns_worker(self):
        dgc.save_config({**dgc.load_config(), "frequency": "manual"})
        with mock.patch.object(dgc, "thread_is_persisted", return_value=True):
            rc, out = run_cli(["probe", "now"], {"CODEX_THREAD_ID": "main-thread-5", "CODEX_SANDBOX_NETWORK_DISABLED": "1"})
        self.assertIn("Queued", out)
        self.assertTrue(dgc.load_session("main-thread-5")["requested"])
        # a Stop hook in that (main) thread launches the background worker, which uses the fake codex
        with mock.patch.object(dgc, "link_session", side_effect=lambda st: st.update(kind="main")), \
                mock.patch.dict(os.environ, {"FAKE_CODEX_MODEL": "gpt-5.6-luna", "FAKE_CODEX_THREAD_MODEL": "gpt-6-astra"}):
            run_hook({"session_id": "main-thread-5", "cwd": TMP, "model": "gpt-6-astra", "hook_event_name": "Stop"})
        deadline = time.time() + 30
        while time.time() < deadline:
            rows = [r for r in dgc.iter_jsonl(dgc.PROBES_INDEX) if r.get("thread_id") == "main-thread-5"]
            if rows:
                break
            time.sleep(0.3)
        self.assertTrue(rows, "worker did not record a probe")
        self.assertEqual(rows[-1]["verdict"], "MISMATCH")
        st = dgc.load_session("main-thread-5")
        self.assertFalse(st["requested"])
        self.assertIsNone(st["probe_running"])
        self.assertEqual(len(st["alerts"]), 1)

    def test_scheduler_spawns_when_due(self):
        dgc.save_config({**dgc.load_config(), "frequency": "turns:2", "mode": "auto"})
        base = {"session_id": "main-thread-6", "cwd": TMP, "model": "gpt-6-astra"}
        with mock.patch.object(dgc, "link_session", side_effect=lambda st: st.update(kind="main")), \
                mock.patch.object(dgc, "spawn_worker", return_value=True) as spawn:
            run_hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "1"})
            run_hook({**base, "hook_event_name": "Stop"})
            spawn.assert_not_called()
            run_hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "2"})
            run_hook({**base, "hook_event_name": "Stop"})
            spawn.assert_called_once()
            run_hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "3"})
            run_hook({**base, "hook_event_name": "Stop"})
            spawn.assert_called_once()  # a probe is marked running; no double launch
        dgc.save_config({**dgc.load_config(), "mode": "nudge"})
        st = dgc.load_session("main-thread-6")
        st["probe_running"], st["turns"], st["last_probe_turn"] = None, 10, 0
        dgc.save_session(st)
        with mock.patch.object(dgc, "link_session", side_effect=lambda st: st.update(kind="main")):
            out = json.loads(run_hook({**base, "hook_event_name": "Stop"}))
        self.assertIn("$is-gpt-nerfed", out["systemMessage"])

    def test_tick_probes_a_due_thread_that_went_quiet(self):
        dgc.save_config({**dgc.load_config(), "frequency": "30m", "mode": "auto"})
        sid = "main-thread-9"
        base = {"session_id": sid, "cwd": TMP, "model": "gpt-6-astra"}
        log_path = os.path.join(os.environ["NERFED_HOME"], "log.jsonl")
        with mock.patch.object(dgc, "link_session", side_effect=lambda st: st.update(kind="main")), \
                mock.patch.object(dgc, "spawn_worker", return_value=True) as spawn:
            run_hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "1"})
            run_hook({**base, "hook_event_name": "Stop"})
            launches = lambda: [c for c in spawn.call_args_list if c.args[0] == sid]  # the ledger is shared with other tests
            rc, out = run_cli(["tick"])
            self.assertEqual(rc, 0, out)
            self.assertEqual(launches(), [])  # a minute old: not due
            self.assertNotIn(sid, out)
            st = dgc.load_session(sid)
            st["created_ts"] = dgc.now() - 31 * 60  # the thread went quiet at minute 29: no Stop event is coming
            dgc.write_json(dgc.session_path(sid), st)
            rc, out = run_cli(["tick"])
            self.assertEqual(len(launches()), 1)
            self.assertIn(sid, out)
            st = dgc.load_session(sid)
            self.assertEqual(st["probe_running"]["probe"], "spawning")
            self.assertGreater(st["last_probe_ts"], dgc.now() - 5)
            run_cli(["tick"])
            self.assertEqual(len(launches()), 1)  # just probed: not due for another 30 minutes
            # due again, but nobody has touched the thread for an hour: whoever was here has left
            st["last_probe_ts"], st["probe_running"] = dgc.now() - 31 * 60, None
            st["updated"] = dgc.iso(dgc.now() - 3600)
            dgc.write_json(dgc.session_path(sid), st)
            run_cli(["tick"])
            self.assertEqual(len(launches()), 1)
            # the next Stop event in that thread runs the schedule as before
            run_hook({**base, "hook_event_name": "Stop"})
            self.assertEqual(len(launches()), 2)
        dgc.save_config({**dgc.load_config(), "mode": "nudge"})
        rc, out = run_cli(["tick"])
        self.assertIn("nothing to launch", out)
        spawns = [e for e in dgc.iter_jsonl(log_path) if e.get("kind") == "worker_spawn" and e.get("sid") == sid]
        self.assertEqual([e.get("via") for e in spawns], ["tick", "hook"])

    def test_self_answer_mode_inside_side_conversation(self):
        rows = fixture_rows()
        astra = [r for r in rows if r["model_id"] == "gpt-6-astra"]
        with mock.patch.object(dgc, "thread_is_persisted", return_value=False), \
                mock.patch.object(dgc, "db_recent_main_thread", return_value={"id": "main-thread-7", "model": "gpt-6-astra"}), \
                mock.patch.object(dgc, "db_thread", side_effect=lambda t: {"id": "main-thread-7", "model": "gpt-6-astra"} if t == "main-thread-7" else None):
            rc, out = run_cli(["probe", "now"], {"CODEX_THREAD_ID": "side-ephemeral-1"})
            self.assertIn("challenge 1/3", out)
            pid = out.split("DGC PROBE ")[1].split()[0]
            rc, out = run_cli(["probe", "submit-numbers", pid, "--numbers", astra[0]["text"]])
            self.assertIn("challenge 2/3", out)
            rc, out = run_cli(["probe", "submit-numbers", pid, "--numbers", "[1, 2, 3]"])
            self.assertIn("will not count", out)
            self.assertIn("challenge 3/3", out)
            rc, out = run_cli(["probe", "submit-numbers", pid, "--numbers", astra[1]["text"]])
        self.assertIn("verdict: MATCH", out)
        self.assertIn("2/3 answers used", out)
        rec = dgc.read_json(dgc.probe_path(pid))
        self.assertEqual(rec["mode"], "self")
        self.assertEqual(rec["thread_id"], "main-thread-7")
        self.assertEqual(rec["side_thread_id"], "side-ephemeral-1")

    def test_report_and_explain(self):
        run_cli(["probe", "now", "--mode", "fork", "--thread", "main-thread-8"], {"FAKE_CODEX_MODEL": "gpt-5.4", "FAKE_CODEX_THREAD_MODEL": "gpt-5.4"})
        pid = [r for r in dgc.iter_jsonl(dgc.PROBES_INDEX) if r["thread_id"] == "main-thread-8"][-1]["id"]
        rc, out = run_cli(["report"])
        self.assertIn(pid, out)
        self.assertIn("MATCH", out)
        rc, out = run_cli(["explain", pid])
        self.assertIn("attribution:", out)
        self.assertIn("gpt-5.4", out)
        rc, out = run_cli(["explain", "--method"])
        self.assertIn("ModelTrace", out)
        rc, out = run_cli(["status"])
        self.assertEqual(rc, 0)

    def test_records_follow_the_signed_in_account(self):
        auth = os.path.join(os.environ["CODEX_HOME"], "auth.json")

        def sign_in(account_id):
            with open(auth, "w") as f:
                json.dump({"auth_mode": "chatgpt", "tokens": {"account_id": account_id}}, f)

        sign_in("account-A")
        a = dgc.current_account()
        self.assertNotIn("account-A", json.dumps(a), "raw account id must never be stored")
        dgc.save_config({**dgc.load_config(), "frequency": "turns:8"})
        base = {"session_id": "acct-thread-A", "cwd": TMP, "model": "gpt-6-astra"}
        with mock.patch.object(dgc, "link_session", side_effect=lambda st: st.update(kind="main")):
            run_hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "1"})
        run_cli(["probe", "now", "--mode", "fork", "--thread", "acct-thread-A"], {"FAKE_CODEX_MODEL": "gpt-6-astra"})
        rec = [r for r in dgc.iter_jsonl(dgc.PROBES_INDEX) if r["thread_id"] == "acct-thread-A"][-1]
        self.assertEqual(rec["account_id"], a["id"])
        snap = json.loads(run_cli(["snapshot", "--json"])[1])
        t = next(t for t in snap["threads"] if t["id"] == "acct-thread-A")
        self.assertFalse(t["unverified"])
        self.assertEqual(t["probes"][0]["id"], rec["id"], "the thread carries its own probe history for the panel's report")
        self.assertIn(rec["id"], t["report_text"])
        self.assertFalse(t["last_probe"]["stale_account"])
        self.assertFalse(t["due"], "just probed under this account")
        # switch accounts: the thread stays (threads are shared), but its verdict no longer vouches for this account
        sign_in("account-B")
        snap = json.loads(run_cli(["snapshot", "--json"])[1])
        t = next(t for t in snap["threads"] if t["id"] == "acct-thread-A")
        self.assertTrue(t["unverified"])
        self.assertTrue(t["last_probe"]["stale_account"])
        self.assertTrue(t["due"], "must be re-probed under the new account")
        self.assertIn("unverified", snap["overall"]["message"])
        self.assertGreaterEqual(snap["overall"]["unverified"], 1)
        self.assertEqual(snap["overall"]["status"], "unverified")
        with mock.patch.object(dgc, "link_session", side_effect=lambda st: st.update(kind="main")), \
                mock.patch.object(dgc, "spawn_worker", return_value=True) as spawn:
            run_hook({**base, "hook_event_name": "Stop"})
            spawn.assert_called_once()
        rc, out = run_cli(["report"])
        self.assertIn("another Codex account", out)
        os.remove(auth)

    def test_pre_tracking_records_are_unknown_and_unverified(self):
        # a record from before accounts were tracked, tagged by the buggy v1 migration (label "", plan None)
        dgc.ensure_dirs()
        rec = {"id": "legacy0001", "mode": "fresh", "thread_id": None, "status": "done", "verdict": "MATCH", "expected": "gpt-6-astra",
               "prediction": "gpt-6-astra", "probability": 1.0, "finished": dgc.iso(), "account": {"id": "deadbeef1234", "label": "", "plan": None}}
        dgc.write_json(dgc.probe_path("legacy0001"), rec)
        dgc.append_jsonl(dgc.PROBES_INDEX, {"id": "legacy0001", "mode": "fresh", "thread_id": None, "status": "done", "verdict": "MATCH",
                                             "expected": "gpt-6-astra", "prediction": "gpt-6-astra", "probability": 1.0,
                                             "finished": dgc.iso(), "account_id": "deadbeef1234"})
        with open(os.path.join(dgc.NERFED_HOME, ".accounts-migrated"), "w") as f:
            f.write("2026-09-15T07:22:34Z\n")  # v1 marker
        snap = json.loads(run_cli(["snapshot", "--json"])[1])
        legacy = next(p for p in snap["recent_probes"] if p["id"] == "legacy0001")
        self.assertEqual(legacy["account_state"], "unknown")
        self.assertTrue(legacy["stale_account"])
        self.assertNotEqual(snap["overall"]["status"], "ok")
        self.assertIn("unverified", snap["overall"]["message"])
        migrated = dgc.read_json(dgc.probe_path("legacy0001"))
        self.assertEqual(migrated["account"]["id"], "unknown")
        with open(os.path.join(dgc.NERFED_HOME, ".accounts-migrated")) as f:
            self.assertTrue(f.read().startswith("v2"))
        rc, out = run_cli(["log", "--kind", "migration", "--json"])
        self.assertIn('"records_marked_unknown": 1', out)

    def test_account_switch_is_logged_and_shown(self):
        auth = os.path.join(os.environ["CODEX_HOME"], "auth.json")
        with open(auth, "w") as f:
            json.dump({"auth_mode": "chatgpt", "tokens": {"account_id": "switch-A"}}, f)
        snap_a = json.loads(run_cli(["snapshot", "--json"])[1])
        with open(auth, "w") as f:
            json.dump({"auth_mode": "chatgpt", "tokens": {"account_id": "switch-B"}}, f)
        snap_b = json.loads(run_cli(["snapshot", "--json"])[1])
        self.assertIsNotNone(snap_b["account"]["switched_ago"])
        self.assertIsNone(snap_a["account"].get("switched_ago") if snap_a["account"].get("switched_at") is None else None)
        rc, out = run_cli(["log", "--kind", "account_switch", "--json"])
        rows = [json.loads(l) for l in out.splitlines() if l.strip()]
        self.assertTrue(rows)
        last = rows[-1]
        self.assertNotIn("switch-A", json.dumps(last))
        self.assertEqual(len(last["from_id"]), 12)
        self.assertNotEqual(last["from_id"], last["to_id"])
        os.remove(auth)

    def test_hide_titles_screenshot_mode(self):
        with mock.patch.object(dgc, "link_session", side_effect=lambda st: st.update(kind="main")):
            run_hook({"session_id": "hide-thread-1", "cwd": TMP, "model": "gpt-6-astra", "hook_event_name": "UserPromptSubmit", "prompt": "x"})
        run_cli(["config", "set", "hide_titles", "true"])
        try:
            snap = json.loads(run_cli(["snapshot", "--json"])[1])
            titles = [t["title"] for t in snap["threads"]]
            self.assertTrue(titles, "test ledger should have threads by now")
            self.assertTrue(all(re.fullmatch(r"Session \d+", t) for t in titles), titles)
            self.assertEqual(snap["account"]["label"], "account hidden")
            self.assertTrue(all(t["cwd"] is None for t in snap["threads"]))
        finally:
            run_cli(["config", "set", "hide_titles", "false"])
        snap = json.loads(run_cli(["snapshot", "--json"])[1])
        self.assertFalse(all(re.fullmatch(r"Thread \d+", t["title"]) for t in snap["threads"]))

    def test_fresh_heartbeat_and_picker_helpers(self):
        self.assertEqual(dgc.coerce_config_value("fresh_frequency", "30m"), "30m")
        with self.assertRaises(ValueError):
            dgc.coerce_config_value("fresh_frequency", "turns:8")
        acct = dgc.current_account()["id"]
        self.assertFalse(dgc.fresh_due({"fresh_frequency": "manual"}, acct))
        self.assertTrue(dgc.fresh_due({"fresh_frequency": "1m"}, "account-with-no-fresh-probes"))
        dgc.append_jsonl(dgc.PROBES_INDEX, {"id": "freshhb01", "mode": "fresh", "thread_id": None, "status": "done", "verdict": "MATCH",
                                             "expected": "gpt-6-astra", "prediction": "gpt-6-astra", "probability": 1.0,
                                             "finished": dgc.iso(), "account_id": "hb-account"})
        self.assertFalse(dgc.fresh_due({"fresh_frequency": "30m"}, "hb-account"), "probed just now")
        dgc.append_jsonl(dgc.PROBES_INDEX, {"id": "freshhb02", "mode": "fresh", "thread_id": None, "status": "done", "verdict": "MATCH",
                                             "expected": "gpt-6-astra", "prediction": "gpt-6-astra", "probability": 1.0,
                                             "finished": dgc.iso(dgc.now() - 3600), "account_id": "hb-old"})
        self.assertTrue(dgc.fresh_due({"fresh_frequency": "30m"}, "hb-old"))
        # CJK-aware column fitting for the picker
        self.assertEqual(dgc.display_width("完成 Exa"), 8)
        self.assertEqual(dgc.display_width(dgc.fit("完成 Exa 小时采集与研究资料消费闭环", 20)), 20)
        self.assertEqual(dgc.fit("abc", 6), "abc   ")
        self.assertTrue(dgc.fit("abcdefghij", 6).endswith("…"))
        self.assertEqual(dgc.display_width(dgc.fit("abcdefghij", 6)), 6)
        snap = json.loads(run_cli(["snapshot", "--json"])[1])
        self.assertIn("fresh_due", snap)

    def test_hook_argv_never_fails(self):
        # Codex treats a non-zero hook exit as a reason to stop the user's turn; argparse would exit 2.
        for argv in (["hook", "--eventUserPromptSubmit"], ["hook", "--event=Stop"], ["hook", "--bogus", "x"], ["hook"]):
            with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"session_id": "argv-test", "cwd": TMP}))), \
                    mock.patch.object(sys.stdin, "isatty", return_value=False, create=True):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    self.assertEqual(dgc.main(argv), 0, argv)
        ev = [e for e in dgc.iter_jsonl(dgc.EVENTS_PATH) if e.get("sid") == "argv-test"]
        self.assertIn("UserPromptSubmit", [e["event"] for e in ev])

    def test_hook_never_crashes(self):
        with mock.patch.object(sys, "stdin", io.StringIO("this is not json")), \
                mock.patch.object(sys.stdin, "isatty", return_value=False, create=True):
            self.assertEqual(dgc.main(["hook"]), 0)



class SnapshotReportTests(unittest.TestCase):
    def setUp(self):
        dgc.save_config({**dgc.DEFAULT_CONFIG, "codex_bin": FAKE_CODEX, "notify": False, "sound": False, "probe_timeout_s": 30})

    def test_snapshot_carries_per_thread_reports(self):
        snap = json.loads(run_cli(["snapshot", "--json", "--demo"])[1])
        t = next(t for t in snap["threads"] if t["id"] == "payments")
        self.assertEqual(t["probes"][0]["id"], t["last_probe"]["id"])
        self.assertEqual(t["probes"][0]["results"][0]["model"], "gpt-5.6-luna")
        self.assertEqual([e["active"] for e in t["evidence"]], [True, False])
        self.assertIn("Fingerprint · gpt-5.6-luna 91%", t["report_text"])
        self.assertIn("reverted", t["report_text"])
        self.assertTrue(snap["global_probes"])
        self.assertTrue(snap["global_report_text"].startswith("is-gpt-nerfed · Fresh session"))
        self.assertIn("Earlier · Match", snap["global_report_text"])

    def test_probe_line_reads_like_the_panel(self):
        line = dgc.probe_line({"id": "abc", "verdict": "MISMATCH", "direction": "downgrade", "prediction": "gpt-5.6-luna", "probability": 0.91,
                               "expected": "gpt-6-astra", "p_expected": 0.03, "used_outputs": 3, "queries": 3, "elapsed_s": 41.2, "finished_ago": "4m ago"})
        self.assertEqual(line, "Downgrade · gpt-5.6-luna 91%, declared 3% · 3 of 3 answers · 41 s · 4m ago · probe abc")
        failed = dgc.probe_line({"id": "def", "verdict": "INVALID", "status": "failed", "errors": ["fork timed out"], "retries": 1})
        self.assertEqual(failed, "Invalid · fork timed out · retried once · probe def")
        stale = dgc.probe_line({"id": "ghi", "verdict": "MATCH", "prediction": "gpt-5.6-sol", "probability": 1.0, "stale_account": True, "account_state": "other"})
        self.assertTrue(stale.startswith("Unverified · Match, another account · "), stale)

    def test_session_start_hook_runs_to_the_end(self):
        # regression: log_event("session_start", kind=...) collided with log_event's own `kind` parameter and every
        # SessionStart hook died in the fail-safe (exit 0, nothing recorded)
        errors = os.path.join(dgc.NERFED_HOME, "errors.log")
        before = open(errors).read() if os.path.exists(errors) else ""
        with mock.patch.object(dgc, "link_session", side_effect=lambda st: st.update(kind="main")):
            run_hook({"session_id": "start-thread-1", "cwd": TMP, "model": "gpt-6-astra", "hook_event_name": "SessionStart", "source": "startup"})
        after = open(errors).read() if os.path.exists(errors) else ""
        self.assertEqual(after, before, "the SessionStart hook must not crash")
        events = [e for e in dgc.iter_jsonl(os.path.join(dgc.NERFED_HOME, "log.jsonl")) if e.get("kind") == "session_start"]
        self.assertTrue(events and events[-1].get("sid") == "start-thread-1" and events[-1].get("session_kind") == "main")

    def test_a_fork_that_times_out_is_replaced_once(self):
        dgc.save_config({**dgc.load_config(), "probe_timeout_s": 4})
        marker = os.path.join(TMP, "hang-once")
        open(marker, "w").close()
        code, out = run_cli(["probe", "fresh", "--model", "gpt-6-astra", "--queries", "2"], {"FAKE_CODEX_MODEL": "gpt-6-astra", "FAKE_CODEX_HANG_ONCE": marker})
        self.assertEqual(code, 0, out)
        rec = dgc.read_json(dgc.probe_path([r for r in dgc.iter_jsonl(dgc.PROBES_INDEX) if r.get("mode") == "fresh"][-1]["id"]))
        self.assertEqual(rec.get("topped_up"), 1, "one fork timed out, one replacement was run")
        self.assertEqual(rec["used_outputs"], 2, "the replacement answer counts")
        self.assertTrue(any("timed out" in e for e in rec["errors"]), rec["errors"])
        self.assertEqual(rec["verdict"], "MATCH")
        dgc.save_config({**dgc.load_config(), "probe_timeout_s": 30})

    def test_config_file_keeps_only_choices_not_frozen_defaults(self):
        before = dgc.load_config()
        dgc.save_config({**dgc.DEFAULT_CONFIG, "frequency": "15m", "codex_bin": FAKE_CODEX})
        on_disk = dgc.read_json(dgc.CONFIG_PATH)
        self.assertEqual(set(on_disk), {"frequency", "codex_bin"}, on_disk)
        dgc.write_json(dgc.CONFIG_PATH, {"probe_timeout_s": 180, "confirm_uncertain": True, "frequency": "15m", "codex_bin": FAKE_CODEX})
        cfg = dgc.load_config()
        self.assertEqual(cfg["probe_timeout_s"], dgc.DEFAULT_CONFIG["probe_timeout_s"], "an old default dump does not freeze the timeout")
        self.assertFalse(cfg["confirm_uncertain"])
        self.assertEqual(cfg["frequency"], "15m", "a real choice survives")
        dgc.save_config(before)

    def test_a_transient_store_error_is_retried(self):
        self.assertTrue(dgc.transport_like(["codex thread/fork: failed to prepare paginated fork: thread-store internal error: thread history projection for x is behind durable rollout"]))
        marker = os.path.join(TMP, "fork-error-once"); open(marker, "w").close()
        with mock.patch.object(dgc, "link_session", side_effect=lambda st: st.update(kind="main")):
            run_hook({"session_id": "store-lag-1", "cwd": TMP, "model": "gpt-6-astra", "hook_event_name": "UserPromptSubmit", "prompt": "hi"})
        code, out = run_cli(["probe", "now", "--mode", "fork", "--thread", "store-lag-1"], {"FAKE_CODEX_MODEL": "gpt-6-astra", "FAKE_CODEX_FORK_ERROR_ONCE": marker})
        self.assertEqual(code, 0, out)
        rec = dgc.read_json(dgc.probe_path([r for r in dgc.iter_jsonl(dgc.PROBES_INDEX) if r.get("thread_id") == "store-lag-1"][-1]["id"]))
        self.assertEqual(rec["retries"], 1, "one retry after Codex's store lagged its rollout")
        self.assertEqual(rec["verdict"], "MATCH")

    def test_an_analysis_without_candidates_is_invalid(self):
        self.assertEqual(dgc.assess("gpt-6-astra", {"results": [], "used_outputs": 3}, [])["verdict"], "INVALID")
        self.assertEqual(dgc.fingerprint_verdict("gpt-6-astra", {"results": []}, []), ("INVALID", None))

    def test_a_mismatch_needs_two_answers(self):
        results = [{"model": "gpt-5.6-luna", "probability": 0.99, "score": 2.0}, {"model": "gpt-6-astra", "probability": 0.01, "score": 0.0}]
        self.assertEqual(dgc.assess("gpt-6-astra", {"results": results, "used_outputs": 1}, [])["verdict"], "SUSPICIOUS")
        self.assertEqual(dgc.assess("gpt-6-astra", {"results": results, "used_outputs": 2}, [])["verdict"], "MISMATCH")

    def test_probes_identify_as_the_client_they_check_for(self):
        self.assertEqual(dgc.default_originator("/Applications/ChatGPT.app/Contents/Resources/codex"), "Codex Desktop")
        self.assertEqual(dgc.default_originator("/opt/homebrew/bin/codex"), "codex_cli_rs")
        self.assertEqual(dgc.resolve_originator({"probe_originator": "auto"}, "/opt/homebrew/bin/codex", {"originator": "Codex Desktop"}), "Codex Desktop")
        self.assertEqual(dgc.resolve_originator({"probe_originator": "my-client"}, "/opt/homebrew/bin/codex", {"originator": "Codex Desktop"}), "my-client")
        self.assertEqual(dgc.resolve_originator({"probe_originator": "auto"}, None, None, "override"), "override")
        code, out = run_cli(["probe", "fresh", "--model", "gpt-6-astra", "--queries", "1", "--originator", "Codex Desktop"], {"FAKE_CODEX_MODEL": "gpt-6-astra"})
        self.assertEqual(code, 0, out)
        rec = dgc.read_json(dgc.probe_path([r for r in dgc.iter_jsonl(dgc.PROBES_INDEX) if r.get("mode") == "fresh"][-1]["id"]))
        self.assertEqual(rec["originator"], "Codex Desktop")
        self.assertEqual(rec["forks"][0].get("originator"), "Codex Desktop", "the fake server saw the override, as the real codex would")
        self.assertIn("as Codex Desktop", dgc.probe_line(dgc.probe_summary({"id": rec["id"], "verdict": "MATCH"})))

    def test_update_check_status_and_versions(self):
        self.assertEqual(dgc.version_tuple("v0.4.2"), (0, 4, 2))
        self.assertGreater(dgc.version_tuple("0.10.0"), dgc.version_tuple("0.9.9"))
        self.assertEqual(dgc.version_tuple(None), (0,))
        dgc.write_json(dgc.UPDATE_PATH, {"checked": dgc.iso(), "latest": "99.0.0", "url": "https://example.test/rel", "error": None})
        u = dgc.update_status({"check_updates": True})
        self.assertTrue(u["available"])
        self.assertEqual((u["latest"], u["url"], u["current"]), ("99.0.0", "https://example.test/rel", dgc.VERSION))
        dgc.write_json(dgc.UPDATE_PATH, {"checked": dgc.iso(), "latest": dgc.VERSION, "error": "HTTP 404"})
        u = dgc.update_status({"check_updates": False})
        self.assertFalse(u["available"])
        self.assertFalse(u["enabled"])
        snap = json.loads(run_cli(["snapshot", "--json"])[1])
        self.assertIn("update", snap)
        self.assertFalse(snap["update"]["available"])
        os.remove(dgc.UPDATE_PATH)

    def test_release_assets_pair_the_zip_with_its_own_checksum(self):
        data = {"assets": [{"name": "IsGPTNerfed-0.4.1.dmg", "browser_download_url": "u/dmg"},
                           {"name": "IsGPTNerfed-0.4.1.dmg.sha256", "browser_download_url": "u/dmg.sha256"},
                           {"name": "IsGPTNerfed-0.4.1.zip", "browser_download_url": "u/zip"},
                           {"name": "IsGPTNerfed-0.4.1.zip.sha256", "browser_download_url": "u/zip.sha256"}]}
        self.assertEqual(dgc.pick_release_assets(data), ("u/zip", "u/zip.sha256"))
        self.assertEqual(dgc.pick_release_assets({"assets": [{"name": "x.zip", "browser_download_url": "u/x"}]}), ("u/x", None))
        self.assertEqual(dgc.pick_release_assets({"assets": []}), (None, None))

    def test_update_install_swaps_the_app_bundle(self):
        import hashlib, plistlib, zipfile
        base = os.path.join(TMP, "update-test"); os.makedirs(base, exist_ok=True)

        def fake_app(root, version):
            os.makedirs(os.path.join(root, "Contents", "MacOS"), exist_ok=True)
            with open(os.path.join(root, "Contents", "Info.plist"), "wb") as f:
                plistlib.dump({"CFBundleShortVersionString": version, "CFBundleIdentifier": "dev.is-gpt-nerfed.menubar"}, f)
            with open(os.path.join(root, "Contents", "MacOS", "IsGPTNerfed"), "w") as f:
                f.write("#!/bin/sh\n")

        installed = os.path.join(base, "Applications", "IsGPTNerfed.app"); fake_app(installed, "0.0.1")
        staged = os.path.join(base, "stage", "IsGPTNerfed.app"); fake_app(staged, "99.0.0")
        zip_path = os.path.join(base, "IsGPTNerfed-99.0.0.zip")
        with zipfile.ZipFile(zip_path, "w") as z:
            for root, _dirs, files in os.walk(staged):
                for name in files:
                    full = os.path.join(root, name)
                    z.write(full, os.path.relpath(full, os.path.dirname(staged)))
        with open(zip_path + ".sha256", "w") as f:
            f.write(hashlib.sha256(open(zip_path, "rb").read()).hexdigest() + "  IsGPTNerfed-99.0.0.zip\n")
        dgc.write_json(dgc.UPDATE_PATH, {"checked": dgc.iso(), "latest": "99.0.0", "url": "https://example.test/rel",
                                         "asset_url": "file://" + zip_path, "sha256_url": "file://" + zip_path + ".sha256", "error": None})
        backups = os.path.join(base, "trash"); os.makedirs(backups)
        code, out = run_cli(["update-install", "--app", installed, "--backup-dir", backups, "--no-launch"])
        self.assertEqual(code, 0, out)
        with open(os.path.join(installed, "Contents", "Info.plist"), "rb") as f:
            self.assertEqual(plistlib.load(f)["CFBundleShortVersionString"], "99.0.0", "the new bundle sits where the old one was")
        self.assertTrue(any(n.startswith("IsGPTNerfed-") and n.endswith(".app") for n in os.listdir(backups)), "the old bundle was kept")
        self.assertEqual(dgc.read_json(dgc.UPDATE_PATH)["status"], "installed")
        # a tampered archive is refused before anything is touched
        with open(zip_path, "ab") as f:
            f.write(b"x")
        fake_app(installed, "0.0.1")
        code, out = run_cli(["update-install", "--app", installed, "--backup-dir", backups, "--no-launch", "--force"])
        self.assertNotEqual(code, 0)
        self.assertIn("sha256 mismatch", dgc.read_json(dgc.UPDATE_PATH)["status"])
        with open(os.path.join(installed, "Contents", "Info.plist"), "rb") as f:
            self.assertEqual(plistlib.load(f)["CFBundleShortVersionString"], "0.0.1", "nothing was replaced")
        os.remove(dgc.UPDATE_PATH)

    def test_upgrade_shows_as_good_news(self):
        snap = json.loads(run_cli(["snapshot", "--json", "--demo"])[1])
        t = next(t for t in snap["threads"] if t["id"] == "docs")
        self.assertTrue(t["upgraded"])
        self.assertEqual(t["last_evidence_severity"], "good")
        self.assertEqual(snap["overall"]["upgraded"], 1)
        self.assertIn("1 upgraded", snap["overall"]["message"])

    def test_failed_attempt_is_not_a_verdict(self):
        snap = json.loads(run_cli(["snapshot", "--json", "--demo"])[1])
        t = next(t for t in snap["threads"] if t["id"] == "oauth")
        self.assertEqual(t["last_probe"]["verdict"], "MATCH", "the row keeps the last verdict")
        self.assertEqual(t["last_failure"]["verdict"], "INVALID")
        self.assertTrue(t["last_failure"]["retryable"])
        self.assertEqual([p["verdict"] for p in t["probes"]], ["MATCH"], "failed attempts stay out of the history")
        self.assertIn("Last attempt · Invalid · codex thread/fork timed out", t["report_text"])
        self.assertEqual(snap["last_verdict"]["id"], "a1b2c3d4e5")
        self.assertFalse(dgc.probe_row_valid({"status": "failed", "verdict": "INVALID"}))
        self.assertTrue(dgc.probe_row_valid({"status": "done", "verdict": "MATCH"}))


class ServedModelTests(unittest.TestCase):
    """The server check: one small request per probe, weighed next to the fingerprint, never instead of it."""

    class SSEHandler(__import__("http.server", fromlist=["BaseHTTPRequestHandler"]).BaseHTTPRequestHandler):
        served_model = "gpt-6-astra"
        header_model = None
        redirect_to = None
        seen = []

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            cls = type(self)
            cls.seen.append(("POST", self.path, {k.lower(): v for k, v in self.headers.items()}, json.loads(body or b"{}")))
            if cls.redirect_to:
                self.send_response(302)
                self.send_header("Location", cls.redirect_to)
                self.end_headers()
                return
            if not (self.headers.get("Authorization") or "").startswith("Bearer "):
                self.send_response(401)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            if cls.header_model:
                self.send_header("OpenAI-Model", cls.header_model)
            self.end_headers()
            ev = {"type": "response.created", "response": {"id": "r1", "model": cls.served_model}}
            self.wfile.write(f"event: response.created\ndata: {json.dumps(ev)}\n\n".encode())
            self.wfile.flush()

        def do_GET(self):  # where a redirect would lead: it must never be reached
            type(self).seen.append(("GET", self.path, {k.lower(): v for k, v in self.headers.items()}, None))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    @staticmethod
    def jwt(exp_offset_s):
        import base64

        def b(d):
            return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
        return f"{b({'alg': 'none'})}.{b({'exp': time.time() + exp_offset_s})}.sig"

    def write_auth(self, **tokens):
        with open(self.auth_path, "w") as f:
            json.dump({"tokens": {"access_token": self.jwt(3600), **tokens}}, f)

    def setUp(self):
        import threading
        from http.server import ThreadingHTTPServer
        self.auth_path = os.path.join(os.environ["CODEX_HOME"], "auth.json")
        self.write_auth()  # no account id: the records stay under the tests' "local" account
        H = self.SSEHandler
        H.served_model, H.header_model, H.redirect_to, H.seen = "gpt-6-astra", None, None, []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/responses"
        self.patcher = mock.patch.object(dgc.responses_meta, "RESPONSES_URL", self.url)
        self.patcher.start()
        dgc.ensure_dirs()
        dgc.save_config({**dgc.DEFAULT_CONFIG, "codex_bin": FAKE_CODEX, "notify": False, "sound": False,
                         "probe_timeout_s": 30, "served_check_timeout_s": 5})
        dgc._BANK = None

    def tearDown(self):
        self.patcher.stop()
        self.server.shutdown()
        self.server.server_close()
        if os.path.exists(self.auth_path):
            os.remove(self.auth_path)

    def fresh(self, model="gpt-6-astra", answers="gpt-6-astra", **env):
        rc, out = run_cli(["probe", "fresh", "--model", model], {"FAKE_CODEX_MODEL": answers, **env})
        self.assertEqual(rc, 0, out)
        pid = re.search(r"probe ([0-9a-f]{10})", out).group(1)
        return out, dgc.read_json(dgc.probe_path(pid))

    def test_the_fingerprint_runs_when_the_server_agrees(self):
        out, rec = self.fresh()
        self.assertIn("verdict: MATCH", out)
        self.assertEqual(len(rec["forks"]), 3, "the server's word never replaces the fingerprint")
        self.assertEqual(rec["server"]["state"], "same")
        self.assertIn("server says gpt-6-astra (as asked)", out)
        self.assertEqual(rec["served"]["requested"], "gpt-6-astra")

    def test_the_server_agreeing_cannot_clear_a_fingerprint_mismatch(self):
        out, rec = self.fresh(answers="gpt-5.6-luna")  # the label says astra, the answers look like luna
        self.assertEqual((rec["verdict"], rec["direction"]), ("MISMATCH", "downgrade"))
        self.assertEqual(rec["server"]["state"], "same")

    def test_both_layers_agree_on_a_downgrade(self):
        self.SSEHandler.served_model = "gpt-5.6-luna"
        out, rec = self.fresh(answers="gpt-5.6-luna")
        self.assertEqual((rec["verdict"], rec["direction"]), ("MISMATCH", "downgrade"))
        self.assertEqual(rec["server"]["state"], "downgrade")
        self.assertIn("server says gpt-5.6-luna for gpt-6-astra (downgrade", out)

    def test_a_server_contradicting_a_match_makes_it_suspicious(self):
        self.SSEHandler.served_model = "gpt-5.6-luna"
        out, rec = self.fresh()  # the answers look like astra
        self.assertEqual((rec["verdict"], rec["direction"], rec["status"]), ("SUSPICIOUS", "server", "done"))
        self.assertIn("the server's own response says gpt-5.6-luna answered your gpt-6-astra request", rec["quote"])
        self.assertTrue(dgc.probe_row_valid(rec), "the panel shows it as a verdict, not as a failed attempt")
        snap = json.loads(run_cli(["snapshot", "--json"])[1])
        g = snap["global_probe"]
        self.assertEqual((g["id"], g["verdict"], g["server_model"], g["server_state"]), (rec["id"], "SUSPICIOUS", "gpt-5.6-luna", "downgrade"))
        self.assertIn("Server · gpt-5.6-luna, asked for gpt-6-astra", snap["global_report_text"])
        out, rec = self.fresh(answers="gpt-5.6-luna")  # the fingerprint made this verdict: its numbers lead
        line = dgc.probe_line(json.loads(run_cli(["snapshot", "--json"])[1])["global_probe"])
        self.assertTrue(line.startswith("Downgrade · gpt-5.6-luna 100%, declared 0% · server: gpt-5.6-luna"), line)
        self.assertTrue(dgc.probe_line(g).startswith("Suspicious · server: gpt-5.6-luna · gpt-6-astra 100%"), dgc.probe_line(g))

    def test_the_server_decides_when_the_forks_give_no_answer(self):
        self.SSEHandler.served_model = "gpt-5.6-luna"
        out, rec = self.fresh(FAKE_CODEX_FAIL="1")
        self.assertEqual((rec["verdict"], rec["direction"], rec["status"]), ("DOWNGRADED!", "server", "done"))
        self.assertIn("the server's own response says gpt-5.6-luna answered", rec["quote"])
        snap = json.loads(run_cli(["snapshot", "--json"])[1])
        self.assertEqual(snap["global_probe"]["id"], rec["id"])
        self.assertTrue(snap["global_alert"], "a downgrade the server admits is an alert in the panel too")
        self.assertIn("Downgraded · server: gpt-5.6-luna", dgc.probe_line(snap["global_probe"]))

    def test_a_dated_snapshot_name_is_the_model_asked_for(self):
        self.SSEHandler.served_model = "gpt-6-astra-2026-08-20"
        out, rec = self.fresh()
        self.assertEqual((rec["verdict"], rec["server"]["state"]), ("MATCH", "same"))

    def test_unknown_names_and_upgrades_change_nothing(self):
        self.SSEHandler.served_model = "gpt-6-astra-internal-x"
        out, rec = self.fresh()
        self.assertEqual((rec["verdict"], rec["server"]["state"]), ("MATCH", "unrecognized"))
        self.SSEHandler.served_model = "gpt-6-astra"
        out, rec = self.fresh(model="gpt-5.6-sol", answers="gpt-5.6-sol")
        self.assertEqual((rec["verdict"], rec["server"]["state"]), ("MATCH", "upgrade"))

    def test_the_header_codex_reads_wins_over_the_body(self):
        self.SSEHandler.header_model = "gpt-5.6-luna"
        r = dgc.responses_meta.check_served_model("gpt-6-astra", os.environ["CODEX_HOME"])
        self.assertEqual((r["served"], r["header_model"], r["body_model"]), ("gpt-5.6-luna", "gpt-5.6-luna", "gpt-6-astra"))

    def test_the_request_is_the_probe_model_and_says_who_sends_it(self):
        self.write_auth(account_id="acct-123")
        r = dgc.responses_meta.check_served_model("gpt-6-astra", os.environ["CODEX_HOME"], effort="xhigh",
                                                  originator="Codex Desktop", client_version="9.9.9")
        self.assertTrue(r["ok"], r)
        method, path, headers, body = self.SSEHandler.seen[-1]
        self.assertEqual((body["model"], body["reasoning"], body["store"]), ("gpt-6-astra", {"effort": "xhigh"}, False))
        self.assertEqual(headers["chatgpt-account-id"], "acct-123")
        self.assertEqual(headers["originator"], "Codex Desktop")
        self.assertEqual(headers["user-agent"], "is-gpt-nerfed/9.9.9")

    def test_a_redirect_is_refused_and_the_token_goes_nowhere_else(self):
        self.SSEHandler.redirect_to = self.url.replace("/responses", "/elsewhere")
        r = dgc.responses_meta.check_served_model("gpt-6-astra", os.environ["CODEX_HOME"])
        self.assertFalse(r["ok"])
        self.assertIn("HTTP 302", r["error"])
        self.assertEqual([m for m, *_ in self.SSEHandler.seen], ["POST"], "the redirect target was never contacted")
        with open(dgc.responses_meta.__file__, encoding="utf-8") as f:
            self.assertNotIn("os.environ", f.read(), "no environment override for the token's destination")

    def test_a_failed_check_changes_nothing(self):
        with mock.patch.object(dgc.responses_meta, "RESPONSES_URL", "http://127.0.0.1:9/none"):
            out, rec = self.fresh()
        self.assertEqual((rec["verdict"], rec["server"]["state"]), ("MATCH", "failed"))
        self.assertIn("server check: no answer", out)

    def test_an_expired_token_is_never_sent(self):
        with open(self.auth_path, "w") as f:
            json.dump({"tokens": {"access_token": self.jwt(-3600)}}, f)
        self.assertEqual(dgc.responses_meta.read_auth(os.environ["CODEX_HOME"]), (None, None))
        out, rec = self.fresh()
        self.assertEqual(self.SSEHandler.seen, [], "no request without a valid token")
        self.assertEqual((rec["verdict"], rec["server"]["state"]), ("MATCH", "failed"))

    def test_switching_it_off_means_no_request(self):
        rc, out = run_cli(["config", "set", "served_check", "false"])
        self.assertIs(dgc.load_config()["served_check"], False, "stored as a boolean, not the truthy string 'false'")
        out, rec = self.fresh()
        self.assertEqual(self.SSEHandler.seen, [])
        self.assertNotIn("served", rec)
        self.assertNotIn("server", rec)

    def test_served_command(self):
        rc, out = run_cli(["served", "--model", "gpt-6-astra"])
        self.assertEqual(rc, 0, out)
        self.assertIn("server says: gpt-6-astra  (the model asked for)", out)
        self.SSEHandler.served_model = "gpt-5.6-luna"
        rc, out = run_cli(["served", "--model", "gpt-6-astra"])
        self.assertEqual(rc, 2, out)
        self.assertIn("server says: gpt-5.6-luna  (a downgrade", out)
        os.remove(self.auth_path)
        rc, out = run_cli(["served", "--model", "gpt-6-astra"])
        self.assertEqual(rc, 1, out)


if __name__ == "__main__":
    unittest.main()
