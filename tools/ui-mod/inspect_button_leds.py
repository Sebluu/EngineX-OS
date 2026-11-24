#!/usr/bin/env python3
"""Read-only inventory of JC11 LED assignments in an extracted Engine QRC tree."""
import argparse
import hashlib
import pathlib
import re

TARGET=re.compile(r"(?i)(blink|flash|pulse|led|light|beatphase|playstate|fxenable|fxon|turnon|turnoff)")
MODEL=re.compile(r"(?i)(jc11|controller|mixer|assignment|jogoutput|led)")
RELEVANT=re.compile(r"(?i)(play|pause|fx|effect|beat)")

def inventory(root):
    for path in sorted(root.rglob("*.qml")):
        rel=path.relative_to(root).as_posix()
        if not MODEL.search(rel): continue
        raw=path.read_bytes()
        text=raw.decode("utf-8",errors="replace")
        if not RELEVANT.search(text): continue
        lines=text.splitlines()
        hits=[i for i,line in enumerate(lines) if TARGET.search(line)]
        if not hits: continue
        print(f"\n--- {rel} sha256={hashlib.sha256(raw).hexdigest()} ---")
        wanted=set()
        for i in hits: wanted.update(range(max(0,i-5),min(len(lines),i+6)))
        prev=-2
        for i in sorted(wanted):
            if i>prev+1:print("...")
            print(f"{i+1:5}: {lines[i]}")
            prev=i

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("qrc",type=pathlib.Path)
    a=p.parse_args()
    if not a.qrc.is_dir():p.error("extracted QRC directory required")
    inventory(a.qrc)
