#!/usr/bin/env python3
"""CPA pluginstore registry.json validator (schema v1 github-release / v2 direct)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
VER_RE = re.compile(r"^[0-9][0-9A-Za-z.+-]*$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "registry.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    sv = data.get("schema_version")
    if sv not in (1, 2):
        raise SystemExit(f"unsupported schema_version {sv}")
    plugins = data.get("plugins") or []
    if not plugins:
        raise SystemExit("plugins empty")
    seen = set()
    for i, p in enumerate(plugins):
        for field in ("id", "name", "description", "author"):
            if not str(p.get(field, "")).strip():
                raise SystemExit(f"plugins[{i}]: missing {field}")
        pid = p["id"].strip()
        if not ID_RE.match(pid):
            raise SystemExit(f"plugins[{i}]: invalid id {pid!r}")
        if pid in seen:
            raise SystemExit(f"duplicate id {pid}")
        seen.add(pid)
        ver = str(p.get("version") or "").strip()
        if ver and not VER_RE.match(ver):
            raise SystemExit(f"plugins[{i}]: invalid version {ver!r}")
        install = p.get("install") or {}
        itype = (install.get("type") or "github-release").strip()
        if itype == "github-release":
            repo = str(p.get("repository") or "").strip()
            if "github.com" not in repo:
                raise SystemExit(f"plugins[{i}]: repository must be github for github-release")
            # Monorepo tags like workbuddy-v0.8.5 fail CPA ReleaseVersion()
            # (expects v0.8.5 / 0.8.5). Prefer install.type=direct for monorepos.
        elif itype == "direct":
            if sv != 2:
                raise SystemExit("direct install requires schema_version 2")
            if not ver:
                raise SystemExit(f"plugins[{i}]: direct install needs version")
            artifacts = install.get("artifacts") or []
            if not artifacts:
                raise SystemExit(f"plugins[{i}]: direct install needs artifacts")
            seen_plat = set()
            for j, art in enumerate(artifacts):
                goos = str(art.get("goos") or "").strip().lower()
                goarch = str(art.get("goarch") or "").strip().lower()
                url = str(art.get("url") or "").strip()
                sha = str(art.get("sha256") or "").strip().lower()
                if not goos or not goarch:
                    raise SystemExit(f"plugins[{i}].artifacts[{j}]: missing goos/goarch")
                key = (goos, goarch)
                if key in seen_plat:
                    raise SystemExit(f"plugins[{i}].artifacts[{j}]: duplicate platform {goos}/{goarch}")
                seen_plat.add(key)
                parsed = urlparse(url)
                if parsed.scheme not in ("http", "https") or not parsed.netloc:
                    raise SystemExit(f"plugins[{i}].artifacts[{j}]: invalid url")
                if parsed.query or parsed.fragment or parsed.username or parsed.password:
                    raise SystemExit(
                        f"plugins[{i}].artifacts[{j}]: url must not contain query/fragment/credentials"
                    )
                if not SHA_RE.match(sha):
                    raise SystemExit(f"plugins[{i}].artifacts[{j}]: invalid sha256")
        else:
            raise SystemExit(f"plugins[{i}]: bad install type {itype}")
    print(f"OK {path}: {len(plugins)} plugin(s), schema_version={sv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
