"""Create/restore the old SUB row geometry in a disposable CI-only fixture."""
import gzip
import io
import os
from pathlib import Path
import sys
import tarfile

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('disposable CI host required')
mode, directory = sys.argv[1:]
work = Path(directory)
archive = work / 'runtime/mods/subharmonic-synth-0.1.1.tar.gz'
backup = work / 'fixed-sub-panel.tar.gz'
if mode == 'stage':
    backup.write_bytes(archive.read_bytes())
    with tarfile.open(backup, 'r:gz') as source:
        files = [(item, source.extractfile(item).read()) for item in source.getmembers()]
    with archive.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as destination:
            for item, content in files:
                if item.name == 'Panel.qml':
                    assert content.count(b'height:40') == 1
                    content = content.replace(b'height:40', b'')
                item.size = len(content)
                destination.addfile(item, io.BytesIO(content))
elif mode == 'restore':
    archive.write_bytes(backup.read_bytes())
    with tarfile.open(backup, 'r:gz') as source:
        panel = source.extractfile('Panel.qml').read()
    # Only this disposable test's installed package is restored. Its enabled
    # state and DSP settings stay untouched, as on the following restart.
    (work / 'data/enginex/mods/subharmonic-synth/Panel.qml').write_bytes(panel)
else:
    raise SystemExit('expected stage or restore')
