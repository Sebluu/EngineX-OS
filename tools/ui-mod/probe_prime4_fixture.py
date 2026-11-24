#!/usr/bin/env python3
"""Bounded read-only evidence from an official unpacked JC11 fixture.
Never upload the vendor firmware, complete QRC or binaries as CI artifacts.
"""
import hashlib
import json
from pathlib import Path
import re
import sys

needle = re.compile(r"(?i)(play|pause|blink|flash|fx.*(?:enable|active|on)|(?:enable|active|on).*fx)")
for root in map(Path, sys.argv[1:]):
    candidates = [p for p in root.rglob("*.qml") if "jc11" in p.name.lower() and "jc11s" not in p.name.lower()]
    print("JC11_FIXTURE_FILES=" + json.dumps([p.relative_to(root).as_posix() for p in candidates]))
    for path in candidates[:12]:
        if path.is_symlink() or path.stat().st_size > 512 * 1024:
            continue
        raw = path.read_bytes()
        lines = raw.decode("utf-8", errors="replace").splitlines()
        hits = [i for i, line in enumerate(lines) if needle.search(line)][:28]
        keep = set()
        for i in hits:
            keep.update(range(max(0, i-2), min(len(lines), i+4)))
        print("JC11_ASSIGNMENT=" + json.dumps({"path": path.relative_to(root).as_posix(),
              "sha256": hashlib.sha256(raw).hexdigest(),
              "lines": [[i+1, lines[i]] for i in sorted(keep)]}))
