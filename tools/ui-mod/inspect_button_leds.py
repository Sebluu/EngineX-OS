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
    found=0
    for path in sorted(root.rglob("*.qml")):
        # The evidence collector never follows a link out of the extracted QRC.
        if path.is_symlink() or any((root / p).is_symlink() for p in path.relative_to(root).parents if p != pathlib.Path('.')):
            continue
        if not path.is_file() or path.stat().st_size > 2*1024*1024:
            continue
        rel=path.relative_to(root).as_posix()
        if not MODEL.search(rel): continue
        raw=path.read_bytes()
        text=raw.decode("utf-8",errors="replace")
        if not RELEVANT.search(text): continue
        lines=text.splitlines()
        hits=[i for i,line in enumerate(lines) if TARGET.search(line)]
        if not hits: continue
        found+=1
        if found>256: raise ValueError("Too many candidate assignment files; narrow the QRC root")
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
    inventory(a.qrc.resolve())

