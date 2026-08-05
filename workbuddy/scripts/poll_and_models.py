#!/usr/bin/env python3
"""Poll CLI login state then fetch models. Uses cookie jar from start_login."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import LWPCookieJar
from pathlib import Path

BASE = "https://copilot.tencent.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "_probe_state.txt"
COOKIE_FILE = HERE / "_probe_cookies.txt"
OUT_FILE = HERE / "_models_redacted.json"


def main() -> int:
    state = STATE_FILE.read_text(encoding="utf-8").strip()
    jar = LWPCookieJar(str(COOKIE_FILE))
    jar.load(ignore_discard=True, ignore_expires=True)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def req(method: str, url: str, body: bytes | None = None, headers: dict | None = None):
        h = {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Origin": BASE,
            "Referer": BASE + "/",
        }
        if headers:
            h.update(headers)
        r = urllib.request.Request(url, data=body, headers=h, method=method)
        try:
            with opener.open(r, timeout=30) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read() if e.fp else b""

    print(f"polling state={state}", flush=True)
    access = ""
    deadline = time.time() + 300
    while time.time() < deadline:
        st, raw = req("GET", f"{BASE}/v2/plugin/auth/token?state={state}")
        try:
            env = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            print(f"nonjson http={st}", flush=True)
            time.sleep(2)
            continue
        code = env.get("code")
        data = env.get("data") or {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                data = {}
        if st == 200 and code in (0, "0") and isinstance(data, dict):
            access = (data.get("accessToken") or data.get("access_token") or "").strip()
            if access:
                print("LOGIN_OK", flush=True)
                break
        print(f"waiting code={code} msg={env.get('msg')}", flush=True)
        time.sleep(2)
    else:
        print("TIMEOUT", flush=True)
        return 2

    st, raw = req(
        "GET",
        f"{BASE}/console/enterprises/personal/models",
        headers={"Authorization": "Bearer " + access},
    )
    access = ""
    print(f"models_http={st}", flush=True)
    env = json.loads(raw.decode("utf-8", "replace"))
    print(f"models_code={env.get('code')}", flush=True)
    data = env.get("data") or {}
    models = data.get("models") or []
    agents = data.get("agents") or []
    cli: list[str] = []
    for a in agents:
        if str(a.get("name", "")).lower() == "cli":
            cli = list(a.get("models") or [])
            break
    enabled = [m for m in models if not m.get("disabled")]
    ids = [str(m.get("id") or "") for m in enabled]
    print(f"enabled_count={len(ids)}", flush=True)
    print("ENABLED_IDS_BEGIN")
    for i in ids:
        print(i)
    print("ENABLED_IDS_END")
    print("CLI_IDS_BEGIN")
    for i in cli:
        print(i)
    print("CLI_IDS_END")
    has_k3 = any(x.lower() == "kimi-k3" or "kimi-k3" in x.lower() for x in ids)
    in_cli = any(x.lower() == "kimi-k3" or "kimi-k3" in x.lower() for x in cli)
    print(f"kimi_k3_in_catalog={has_k3}")
    print(f"kimi_k3_in_cli={in_cli}")
    for m in enabled:
        mid = str(m.get("id") or "")
        if "kimi" in mid.lower() or "k3" in mid.lower():
            print(f"kimi_entry id={mid} name={m.get('name')}")
    red = {
        "cli": cli,
        "models": [
            {"id": m.get("id"), "name": m.get("name"), "disabled": bool(m.get("disabled"))}
            for m in models
        ],
    }
    OUT_FILE.write_text(json.dumps(red, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SAVED_REDACTED_CATALOG", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
