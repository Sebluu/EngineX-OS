"""Encode preview frames on the VM's x86 CPU, outside the emulated ARM GUI."""
import io
import json
import math
import os
from pathlib import Path
import sys
import time

from PIL import Image


def read_frame(path):
    with Path(path).open('rb') as stream:
        header = stream.readline(2049)
        if len(header) > 2048 or not header.endswith(b'\n'):
            raise ValueError('invalid frame header')
        meta = json.loads(header)
        for name, limit in (('width', 1280), ('height', 800)):
            if type(meta.get(name)) is not int or not 1 <= meta[name] <= limit:
                raise ValueError('invalid frame dimensions')
        if meta.get('stride') != meta['width'] * 4 or meta.get('format') != 'RGBA':
            raise ValueError('invalid pixel layout')
        if type(meta.get('frame')) is not int or meta['frame'] < 1:
            raise ValueError('invalid frame number')
        if not isinstance(meta.get('stream'), str) or len(meta['stream']) > 64:
            raise ValueError('invalid frame stream')
        for name in ('capturedAtMs', 'readbackMs'):
            if type(meta.get(name)) not in (int, float) or not math.isfinite(meta[name]) or meta[name] < 0:
                raise ValueError('invalid frame timing')
        size = meta['stride'] * meta['height']
        pixels = stream.read(size + 1)
        if len(pixels) != size:
            raise ValueError('incomplete frame')
    return meta, pixels


def encode_frame(runtime, previous=None):
    runtime = Path(runtime)
    path = runtime / 'frame.raw'
    stamp = path.stat().st_mtime_ns
    if stamp == previous:
        return previous
    meta, pixels = read_frame(path)
    session = (runtime / 'engine.session').read_text().strip()
    if meta['stream'] != session:
        return stamp
    started = time.monotonic()
    image = Image.frombytes('RGBA', (meta['width'], meta['height']), pixels)
    # OpenGL's origin is bottom-left; the browser and Qt input use top-left.
    image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM).convert('RGB')
    output = io.BytesIO()
    image.save(output, format='PNG', compress_level=1)
    meta['encodeMs'] = round((time.monotonic() - started) * 1000, 2)
    for name in ('stride', 'format'):
        del meta[name]
    if (runtime / 'engine.session').read_text().strip() != session or not path.exists():
        return stamp
    (runtime / 'frame.new.png').write_bytes(output.getvalue())
    os.replace(runtime / 'frame.new.png', runtime / 'frame.png')
    (runtime / 'frame.new.json').write_text(json.dumps(meta))
    os.replace(runtime / 'frame.new.json', runtime / 'frame.json')
    return stamp


def main():
    runtime = Path(sys.argv[1])
    previous = None
    while True:
        try:
            previous = encode_frame(runtime, previous)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        time.sleep(.02)


if __name__ == '__main__':
    main()
