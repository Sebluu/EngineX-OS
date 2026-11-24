#!/usr/bin/env python3
"""Local browser frontend for the VM's isolated Engine process. No cloud services."""
import argparse
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent

def inside_vm():
    try:
        product = Path('/sys/class/dmi/id/product_name').read_text()
        return Path('/run/enginex-preview-vm').read_text() == 'local-vm-only\n' and ('QEMU' in product or 'Standard PC' in product)
    except OSError:
        return False

def packet(body, width, height):
    if body.get('kind') == 'pointer':
        action = {'down': 1, 'move': 2, 'up': 3}.get(body.get('action'))
        x, y = body.get('x'), body.get('y')
        button, buttons, mods = body.get('button', 0), body.get('buttons', 0), body.get('mods', 0)
        if action is None or any(type(v) not in (int, float) or not math.isfinite(v) for v in (x, y)):
            raise ValueError('invalid pointer')
        if not (0 <= x < width and 0 <= y < height) or button not in (0, 1, 2, 4):
            raise ValueError('pointer outside frame')
        if type(buttons) is not int or not 0 <= buttons <= 7 or type(mods) is not int or mods & ~0x1e000000:
            raise ValueError('invalid pointer state')
        return f'M {action} {x:.3f} {y:.3f} {button} {buttons} {mods}'.encode()
    if body.get('kind') == 'key':
        action = {'down': 1, 'up': 3}.get(body.get('action'))
        key, mods, text = body.get('key'), body.get('mods', 0), body.get('text', 0)
        if action is None or any(type(v) is not int for v in (key, mods, text)):
            raise ValueError('invalid key')
        if not 0 <= key <= 0x1ffffff or not 0 <= text <= 0x10ffff or 0xd800 <= text <= 0xdfff or mods & ~0x1e000000:
            raise ValueError('invalid key range')
        return f'K {action} {key} {mods} {text}'.encode()
    raise ValueError('unknown input')

class PreviewServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, runtime, data, public_port=None):
        self.runtime, self.data = Path(runtime), Path(data)
        super().__init__(address, Handler)
        self.public_port = public_port or self.server_address[1]

    def meta(self):
        try:
            value = json.loads((self.runtime / 'frame.json').read_text())
            if any(type(value.get(k)) is not int or not 0 < value[k] < 10000 for k in ('width', 'height')):
                return {}
            return {k: value[k] for k in ('width', 'height', 'frame', 'renderer')}
        except (OSError, ValueError, KeyError):
            return {}

    def feedback(self, note=''):
        # Explicit whitelist: no access tokens, account files, library titles or raw logs.
        result = {'schema': 1, 'runtime': 'local QEMU preview', 'uiOnly': True,
                  'note': note[:2000], 'frame': self.meta()}
        try:
            build = json.loads((self.runtime / 'build.json').read_text())
            result['sourceCommit'] = str(build.get('sourceCommit', ''))[:64]
        except (OSError, ValueError):
            pass
        try:
            text = (self.data / 'enginex/ui/output-dsp-v1.conf').read_text()
            values = [float(n) for n in text.split()]
            if len(values) == 140 and all(math.isfinite(n) for n in values):
                result['dspProfiles'] = [values[i:i+35] for i in range(0, 140, 35)]
        except (OSError, ValueError):
            pass
        return result

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def allowed(self, mutation=False):
        host = self.headers.get('Host', '')
        if host not in (f'localhost:{self.server.public_port}', f'127.0.0.1:{self.server.public_port}', f'[::1]:{self.server.public_port}'):
            return False
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return False
        origin = self.headers.get('Origin')
        return not origin or origin == 'http://' + host

    def send(self, status, body=b'', content='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.allowed():
            self.send(403); return
        path = urlsplit(self.path).path
        if path in ('/', '/app.js', '/style.css'):
            name, kind = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}[path]
            self.send(200, (HERE / name).read_bytes(), kind)
        elif path == '/api/status':
            self.send(200, json.dumps({'uiOnly': True, 'frame': self.server.meta()}).encode())
        elif path == '/frame.png':
            try: self.send(200, (self.server.runtime / 'frame.png').read_bytes(), 'image/png')
            except OSError: self.send(503)
        else:
            self.send(404)

    def do_POST(self):
        if not self.allowed(True):
            self.send(403); return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 8192: raise ValueError('invalid size')
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict): raise ValueError('object required')
            path = urlsplit(self.path).path
            if path == '/api/input':
                meta = self.server.meta()
                if not meta: self.send(503); return
                message = packet(body, meta['width'], meta['height'])
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as control:
                    control.sendto(message, str(self.server.runtime / 'control.sock'))
                self.send(200, b'{}')
            elif path == '/api/feedback':
                note = body.get('note', '')
                if not isinstance(note, str): raise ValueError('invalid note')
                self.send(200, json.dumps(self.server.feedback(note), ensure_ascii=False, indent=2).encode())
            elif path == '/api/restart':
                (self.server.runtime / 'restart.request').write_text('restart\n')
                self.send(200, b'{}')
            elif path == '/api/stop':
                if not inside_vm(): self.send(403); return
                self.send(200, b'{}')
                threading.Thread(target=lambda: subprocess.run(['/usr/bin/systemctl','poweroff'],check=False),daemon=True).start()
            else:
                self.send(404)
        except (ValueError, TypeError):
            self.send(400)
        except OSError:
            self.send(503)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--public-port', type=int, default=None)
    parser.add_argument('--listen', default='127.0.0.1')
    args = parser.parse_args()
    if args.listen != '127.0.0.1' and not inside_vm():
        parser.error('non-loopback listener is allowed only inside the preview VM')
    PreviewServer((args.listen, args.port), args.runtime, args.data,args.public_port).serve_forever()

if __name__ == '__main__':
    main()
