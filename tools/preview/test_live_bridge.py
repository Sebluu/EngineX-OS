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
        blue = sum(b > 200 and r < 80 and g < 80 for r, g, b in image.getdata())
        target = re.search(r'PREVIEW_TARGET\|([0-9.]+)\|([0-9.]+)\|', log.read_text(errors='replace'))
        if meta['width'] == image.width and meta['height'] == image.height and red > 3000 and blue > 3000 and meta['renderer'] == 'opengl' and target:
            break
    except (OSError, ValueError, KeyError):
        pass
    time.sleep(.5)
else:
    raise SystemExit('real Engine framebuffer, custom scene-graph geometry or CI input target was not rendered')

print('PASS full OpenGL scene graph: custom geometry rendered in the original Engine, without a host GPU')
assert meta.get('encodeMs') is not None and meta.get('readbackMs') is not None, 'native frame encoder metrics missing'
print('Frame timing: readback={} ms, x86 PNG={} ms'.format(meta['readbackMs'], meta['encodeMs']))

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
print('PASS preview-only DSP capabilities and persisted EQ/SUB parameter edits')

for section in ('eq', 'sub'):
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        client.sendto(('D '+section).encode(), str(runtime/'control.sock'))
    deadline=time.monotonic()+40
    while time.monotonic()<deadline:
        if 'PREVIEW_MOD_PANEL_READY section='+section in log.read_text(errors='replace'):
            loaded_frame=json.loads((runtime/'frame.json').read_text())['frame']
            while time.monotonic()<deadline:
                if json.loads((runtime/'frame.json').read_text())['frame']>=loaded_frame+2:
                    break
                time.sleep(.1)
            else:
                raise SystemExit('the loaded '+section+' panel did not render fresh frames')
            print('PASS original Engine: combined-branch '+section+' settings panel loaded with real SDK data and rendered fresh frames')
            break
        time.sleep(.25)
    else:
        raise SystemExit('the original Engine could not open the '+section+' Mod settings panel')

# Exercise the actual Mod controls, not only its HTTP endpoint.
controls=re.search(r'PREVIEW_SUB_CONTROLS ([0-9.]+) ([0-9.]+) ([0-9.]+) ([0-9.]+) ([0-9.]+) ([0-9.]+)',log.read_text(errors='replace'))
assert controls, 'visible SUB slider and Apply button were not found'
sx,sy,ex,ey,ax,ay=map(float,controls.groups())
def pointer(action,x,y):
    with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as client:
        client.sendto(f'M {action} {x} {y} {int(action!=2)} {int(action!=3)} 0'.encode(),str(runtime/'control.sock'))
    time.sleep(.15)
def next_frames():
    before=json.loads((runtime/'frame.json').read_text())['frame']
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        if json.loads((runtime/'frame.json').read_text())['frame']>=before+2:return
        time.sleep(.1)
    raise SystemExit('Mod controls did not produce fresh frames')
pointer(1,sx,sy);pointer(2,ex,ey);pointer(3,ex,ey)
next_frames()
pointer(1,ax,ay);pointer(3,ax,ay)
deadline=time.monotonic()+15
while time.monotonic()<deadline:
    state=dsp()
    if state['profiles'][0][3]>60:break
    time.sleep(.2)
else:raise SystemExit('dragging the actual SUB strength slider and tapping Apply did not save the value')
next_frames()
saved.write_text(json.dumps(state['profiles']))
print('PASS original Engine: real SUB slider drag and Apply saved settings through the SDK')
