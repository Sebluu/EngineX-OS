"""Assert actual ARM Engine capture and pointer/key delivery in a disposable rootfs."""
import json
from pathlib import Path
import socket
import sys
import time
from PIL import Image

runtime, log = map(Path, sys.argv[1:])
deadline = time.monotonic() + 120
while time.monotonic() < deadline:
    try:
        meta = json.loads((runtime / 'frame.json').read_text())
        image = Image.open(runtime / 'frame.png').convert('RGB')
        red = sum(r > 200 and g < 80 and b < 80 for r, g, b in image.crop((20, 20, 130, 130)).getdata())
        if meta['width'] == image.width and meta['height'] == image.height and red > 3000:
            break
    except (OSError, ValueError, KeyError):
        pass
    time.sleep(.5)
else:
    raise SystemExit('real Engine framebuffer or CI input target was not rendered')

with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
    for packet in (b'M 1 60 60 1 1 0', b'M 3 60 60 1 0 0', b'K 1 65 0 97', b'K 3 65 0 97'):
        client.sendto(packet, str(runtime / 'control.sock'))
        time.sleep(.15)
deadline = time.monotonic() + 15
while time.monotonic() < deadline:
    text = log.read_text(errors='replace')
    if 'PREVIEW_MOUSE_PASS' in text and 'PREVIEW_KEY_PASS' in text:
        print('PASS original ARM Engine: PNG capture, real mouse click and keyboard event')
        break
    time.sleep(.25)
else:
    raise SystemExit('original Engine did not acknowledge real input events')
