"""The server's own answer to "which model served this request?", as a second opinion next to the fingerprint.

Codex's backend can name the model behind a response in two places: the `OpenAI-Model` response header, which
Codex itself compares with the requested model (it logs "server reported model …" and raises a ModelReroute event
on a difference), and `response.model` in the stream's first event, `response.created`, which Codex does not read.
check_served_model() makes one small streaming request with the model and reasoning effort a probe is about to
fingerprint, reads both, and closes the connection at that first event.

What the server says is a label, not a measurement: it can confirm a switch the server admits, it cannot rule out
one it does not. The fingerprint stays the judge of which weights answered.

Token handling. The access token from Codex's auth.json is used only while its JWT `exp` is in the future, and it
is sent only to RESPONSES_URL, a constant: no environment override, and a redirect is an error rather than a hop
(urllib would otherwise repeat the Authorization header to wherever a 3xx points). The refresh token is never read:
OpenAI rotates refresh tokens on use, and a plugin that consumed one would break the user's Codex login.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request

RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
MODEL_HEADERS = ("openai-model", "x-openai-model")  # what Codex's own client reads (codex-api sse/responses.rs)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """The bearer token goes to RESPONSES_URL and nowhere else: a 3xx surfaces as an HTTPError."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _jwt_payload(token: str) -> dict:
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))
    except Exception:
        return {}


def read_auth(codex_home: str, skew_s: float = 60) -> tuple[str | None, str | None]:
    """(access token, ChatGPT account id) from Codex's auth.json. The token only while its JWT exp is valid;
    (None, None) for an API-key login, a missing file or an expired token."""
    try:
        with open(os.path.join(codex_home, "auth.json"), encoding="utf-8") as f:
            tokens = (json.load(f) or {}).get("tokens") or {}
    except Exception:
        return None, None
    tok = tokens.get("access_token")
    if not isinstance(tok, str) or tok.count(".") != 2:
        return None, None
    if float(_jwt_payload(tok).get("exp") or 0) - time.time() < skew_s:
        return None, None
    account = tokens.get("account_id")
    return tok, (account if isinstance(account, str) and account else None)


def check_served_model(model: str, codex_home: str, effort: str | None = None, timeout_s: float = 10,
                       originator: str = "codex_cli_rs", client_version: str = "") -> dict:
    """Ask the backend which model serves `model` (at `effort`) for the signed-in account right now.

    Returns {"ok", "requested", "effort", "served", "header_model", "body_model", "request_id", "elapsed_s", "error"}.
    `served` is the header's model when the server sends one (Codex's own source of truth), else response.model.
    The request carries the account id Codex sends (ChatGPT-Account-Id), identifies as the client the probe runs as
    (`originator`, like the forks) and names itself in the User-Agent."""
    out = {"ok": False, "requested": model, "effort": effort, "served": None, "header_model": None, "body_model": None,
           "request_id": None, "elapsed_s": None, "error": None}
    token, account = read_auth(codex_home)
    if not token:
        out["error"] = "no valid ChatGPT access token (API-key login, signed out, or expired)"
        return out
    body = {
        "model": model,
        "instructions": "You are Codex.",
        "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "say ok"}]}],
        "store": False,
        "stream": True,
    }
    if effort:
        body["reasoning"] = {"effort": effort}  # the probe's effort: routing may depend on it
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "OpenAI-Beta": "responses=v1",
        "originator": originator,
        "User-Agent": f"is-gpt-nerfed/{client_version or '0'}",
    }
    if account:
        headers["ChatGPT-Account-Id"] = account
    req = urllib.request.Request(RESPONSES_URL, data=json.dumps(body).encode(), headers=headers, method="POST")
    t0 = time.time()
    try:
        with _OPENER.open(req, timeout=timeout_s) as resp:
            out["request_id"] = resp.headers.get("x-oai-request-id") or resp.headers.get("x-request-id")
            out["header_model"] = next((resp.headers.get(h) for h in MODEL_HEADERS if resp.headers.get(h)), None)
            deadline = t0 + timeout_s
            while time.time() < deadline:
                line = resp.readline()
                if not line:
                    break
                line = line.strip()
                if not line.startswith(b"data:"):
                    continue
                try:
                    ev = json.loads(line[5:].strip())
                except Exception:
                    continue
                kind = ev.get("type")
                if kind in ("error", "response.failed"):
                    err = ev.get("error") or (ev.get("response") or {}).get("error") or {}
                    out["error"] = f"server error: {(err.get('message') if isinstance(err, dict) else err) or kind}"[:200]
                    break
                if kind == "response.created":
                    out["body_model"] = (ev.get("response") or {}).get("model")
                    break
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read(200).decode("utf-8", "replace").strip()
        except Exception:
            pass
        out["error"] = f"HTTP {e.code}" + (f": {detail}" if detail else "")
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"[:200]
    out["elapsed_s"] = round(time.time() - t0, 2)
    out["served"] = out["header_model"] or out["body_model"]
    if out["served"]:
        out["ok"], out["error"] = True, None
    elif not out["error"]:
        out["error"] = "the stream ended before response.created"
    return out
