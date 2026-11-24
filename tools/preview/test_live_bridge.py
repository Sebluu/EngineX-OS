"""Assert actual ARM Engine capture and pointer/key delivery in a disposable rootfs."""
import json
from pathlib import Path
import socket
import re
import sys
import time
from urllib.request import Request, urlopen
from PIL import Image

runtime, log = map(Path, sys.argv[1:])
deadline = time.monotonic() + 120
while time.monotonic() < deadline:
    try:
        meta = json.loads((runtime / 'frame.json').read_text())
        image = Image.open(runtime / 'frame.png').convert('RGB')
        red = sum(r > 200 and g < 80 and b < 80 for r, g, b in image.getdata())
        target = re.search(r'PREVIEW_TARGET\|([0-9.]+)\|([0-9.]+)\|', log.read_text(errors='replace'))
        if meta['width'] == image.width and meta['height'] == image.height and red > 3000 and target:
            break
    except (OSError, ValueError, KeyError):
        pass
    time.sleep(.5)
else:
    raise SystemExit('real Engine framebuffer or CI input target was not rendered')

x,y=target.groups()
with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
    for packet in (f'M 1 {x} {y} 1 1 0'.encode(), f'M 3 {x} {y} 1 0 0'.encode(), b'K 1 65 0 97', b'K 3 65 0 97'):
        client.sendto(packet, str(runtime / 'control.sock'))
        time.sleep(.15)
deadline = time.monotonic() + 15
while time.monotonic() < deadline:
    text = log.read_text(errors='replace')
    if 'PREVIEW_MOUSE_PASS' in text and 'PREVIEW_KEY_PASS' in text:
        print('PASS original ARM Engine: PNG capture, real pointer/touch and keyboard event')
        break
    time.sleep(.25)
else:
    raise SystemExit('original Engine did not acknowledge real input events')

def dsp(body=None):
    request = Request('http://127.0.0.1:8080/v1/enginex/output-dsp',
                      data=json.dumps(body).encode() if body is not None else None,
                      headers={'Content-Type':'application/json'})
    with urlopen(request,timeout=5) as response:
        return json.load(response)

state = dsp()
assert state['available'] == 3 and state['enabled'] == 3 and state['rate'] == 48000, state
saved = runtime/'smoke-saved.json'
if saved.exists():
    assert state['profiles'] == json.loads(saved.read_text()), 'settings lost after full sandbox restart'
    print('PASS preview settings survived Engine and backend restart')
values = list(state['profiles'][0]); values[0] = 1; values[28] = -3
state = dsp({'section':'eq','pair':0,'values':values})
values = list(state['profiles'][0]); values[2] = 1; values[3] = 35
state = dsp({'section':'sub','pair':0,'values':values})
assert state['profiles'][0][0] == 1 and state['profiles'][0][2] == 1 and state['profiles'][0][28] == -3
saved.write_text(json.dumps(state['profiles']))
print('PASS preview-only DSP capabilities and persisted EQ/SUB parameter edits')
