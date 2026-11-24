#!/usr/bin/env python3
"""Build experimental QML-only Mods. Never build, patch or install firmware."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[2]
MODS = [('output-equalizer', 'Output Equalizer', 'eq', True, False),
        ('subharmonic-synth', 'Subharmonic Synthesizer', 'sub', False, True)]

def files(mid, title, section, eq, sub):
    panel = (ROOT / 'tools/ui-mod/output_dsp_panel.qml').read_text()
    panel = panel.replace('@SECTION@', section).replace('@EQ@', str(eq).lower()).replace('@SUB@', str(sub).lower())
    manifest = dict(id=mid, name=title, version='0.1.0', author='Sebluu',
                    description='Experimental PRIME 4 JC11 controls. Requires the matching native output DSP core; does nothing on stock firmware.',
                    category='audio', homepage='https://github.com/Sebluu/EngineX-OS',
                    qmlFiles={'Panel.qml': f'EngineXMods/{mid}/Panel.qml'})
    return {'mod.json': (json.dumps(manifest, indent=2) + '\n').encode(),
            'Panel.qml': panel.encode(),
            'README.md': (ROOT / 'docs/mods/src' / mid / 'README.md').read_bytes()}

def build(destination):
    destination.mkdir(parents=True, exist_ok=True)
    sums = []
    for mid, title, section, eq, sub in MODS:
        data = files(mid, title, section, eq, sub)
        path = destination / f'{mid}-0.1.0.tar.gz'
        with path.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0, filename='') as gz:
            with tarfile.open(fileobj=gz, mode='w') as tar:
                for name, content in sorted(data.items()):
                    entry = tarfile.TarInfo(name); entry.size = len(content); entry.mode = 0o644
                    tar.addfile(entry, io.BytesIO(content))
        sums.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name)
    (destination / 'SHA256SUMS.txt').write_text('\n'.join(sums) + '\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    build(args.out)
