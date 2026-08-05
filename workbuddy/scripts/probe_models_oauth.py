#!/usr/bin/env python3
"""Authorized local probe: CodeBuddy CLI OAuth → models catalog.

Usage:
  python scripts/probe_models_oauth.py

Flow:
  1) POST /v2/plugin/auth/state?platform=CLI  (cookie jar)
  2) Print AuthURL for user to open / scan WeChat
  3) Poll /v2/plugin/auth/token?state=... until access token
  4) GET /console/enterprises/personal/models
  5) Print model ids (highlight kimi-k3) then wipe token from memory

Does NOT write tokens to disk. For the account owner only.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

BASE = "https://copilot.tencent.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
ORIGIN = "https://copilot.tencent.com"
POLL_TTL_S = 300
POLL_INTERVAL_S = 2.0


class Client:
    def __init__(self) -> None:
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> tuple[int, bytes]:
        h = {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Origin": ORIGIN,
            "Referer": ORIGIN + "/",
        }
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=body, headers=h, method=method)
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read() if e.fp else b""


def envelope(data: bytes) -> dict:
    obj = json.loads(data.decode("utf-8", errors="replace"))
    if not isinstance(obj, dict):
        raise RuntimeError(f"non-object response: {data[:200]!r}")
    return obj


def main() -> int:
    c = Client()
    print("[1] POST auth/state ...", flush=True)
    status, raw = c.request(
        "POST",
        f"{BASE}/v2/plugin/auth/state?platform=CLI",
        body=b"{}",
        headers={"Content-Type": "application/json"},
    )
    if status >= 400:
        print(f"auth/state HTTP {status}: {raw[:300]!r}", file=sys.stderr)
        return 1
    env = envelope(raw)
    if env.get("code", 0) not in (0, None) and env.get("code") != 0:
        # some gateways use code==0 only
        if env.get("code") not in (0, "0"):
            print(f"auth/state business error: {env}", file=sys.stderr)
            # still try data if present
    data = env.get("data") or env
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            pass
    if not isinstance(data, dict):
        print(f"unexpected auth/state payload: {env}", file=sys.stderr)
        return 1
    state = (data.get("state") or data.get("State") or "").strip()
    auth_url = (data.get("authUrl") or data.get("auth_url") or data.get("AuthURL") or "").strip()
    if not state or not auth_url:
        print(f"missing state/authUrl: {json.dumps(env, ensure_ascii=False)[:800]}", file=sys.stderr)
        return 1

    print()
    print("=" * 60)
    print("请在浏览器打开下面链接，用微信扫码登录你自己的 CodeBuddy 账号：")
    print(auth_url)
    print("=" * 60)
    print(f"state={state}")
    print(f"将轮询最多 {POLL_TTL_S}s … 登录成功后自动拉模型列表")
    print()

    access = ""
    refresh = ""
    deadline = time.time() + POLL_TTL_S
    while time.time() < deadline:
        st, raw = c.request("GET", f"{BASE}/v2/plugin/auth/token?state={state}")
        try:
            env = envelope(raw)
        except Exception:
            print(f"  poll HTTP {st} non-json", flush=True)
            time.sleep(POLL_INTERVAL_S)
            continue
        code = env.get("code")
        payload = env.get("data") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        if st == 200 and code in (0, "0") and isinstance(payload, dict):
            access = (payload.get("accessToken") or payload.get("access_token") or "").strip()
            refresh = (payload.get("refreshToken") or payload.get("refresh_token") or "").strip()
            if access:
                print("[2] login OK (token acquired, not saved)", flush=True)
                break
        msg = env.get("msg") or env.get("message") or "pending"
        print(f"  … waiting ({msg}) HTTP={st} code={code}", flush=True)
        time.sleep(POLL_INTERVAL_S)
    else:
        print("login timed out", file=sys.stderr)
        return 2

    # account (optional)
    st, raw = c.request(
        "GET",
        f"{BASE}/v2/plugin/login/account?state={state}",
        headers={"Authorization": f"Bearer {access}"},
    )
    nick = uid = ""
    try:
        env = envelope(raw)
        acc = env.get("data") or {}
        if isinstance(acc, dict):
            nick = str(acc.get("nickname") or acc.get("Nickname") or "")
            uid = str(acc.get("uid") or acc.get("UID") or "")
    except Exception:
        pass
    print(f"[3] account nickname={nick!r} uid={uid[:6]+'…' if len(uid)>6 else uid!r}")

    print("[4] GET personal/models …", flush=True)
    st, raw = c.request(
        "GET",
        f"{BASE}/console/enterprises/personal/models",
        headers={
            "Authorization": f"Bearer {access}",
            "Accept": "application/json",
        },
    )
    # wipe secrets ASAP from locals we no longer need
    access = ""
    refresh = ""

    if st >= 400:
        print(f"models HTTP {st}: {raw[:500]!r}", file=sys.stderr)
        return 3
    env = envelope(raw)
    if env.get("code") not in (0, "0", None):
        # code 0 required
        if env.get("code") != 0:
            print(f"models business error: code={env.get('code')} msg={env.get('msg')}", file=sys.stderr)
            print(raw[:500].decode("utf-8", "replace"), file=sys.stderr)
            return 3
    data = env.get("data") or {}
    models = data.get("models") or []
    agents = data.get("agents") or []
    cli_ids: list[str] = []
    for a in agents:
        if str(a.get("name", "")).lower() == "cli":
            cli_ids = list(a.get("models") or [])
            break

    enabled = [m for m in models if not m.get("disabled")]
    ids = [str(m.get("id") or "") for m in enabled]
    print(f"[5] models total={len(models)} enabled={len(enabled)} cli_agent_ids={len(cli_ids)}")
    print("    enabled ids:")
    for mid in ids:
        mark = "  <== K3" if "k3" in mid.lower() or mid.lower() == "kimi-k3" else ""
        print(f"      - {mid}{mark}")
    if cli_ids:
        print("    cli agent order:")
        for mid in cli_ids:
            mark = "  <== K3" if "k3" in mid.lower() else ""
            in_catalog = mid in ids
            print(f"      - {mid}  catalog_enabled={in_catalog}{mark}")

    has_k3 = any(x.lower() == "kimi-k3" or "kimi-k3" in x.lower() for x in ids)
    in_cli = any(x.lower() == "kimi-k3" or "kimi-k3" in x.lower() for x in cli_ids)
    print()
    print(f"RESULT: kimi-k3 in enabled catalog = {has_k3}")
    print(f"RESULT: kimi-k3 in cli agent list  = {in_cli}")
    if has_k3 and not in_cli:
        print("NOTE: K3 is in catalog but NOT in cli agent list — old plugin would drop it;")
        print("      new parseModelsAPIBody keeps catalog extras.")
    if not has_k3:
        print("NOTE: upstream catalog has no kimi-k3 for this account (plan/region).")
        print("      static fallback still lists kimi-k3 after our code change.")

    # also dump names for a few
    print()
    print("sample name map:")
    for m in enabled[:20]:
        print(f"  {m.get('id')}: {m.get('name')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
