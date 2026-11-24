"""Exercise real browser gestures before downloading or starting firmware.

Only the framebuffer and Engine's input socket are fixtures. The local HTTP
server, frontend, Chrome input processing and CSS are the production preview.
"""
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import uuid

from PIL import Image
from server import PreviewServer


def main():
    chrome = shutil.which('google-chrome') or shutil.which('chromium')
    if not chrome:
        raise SystemExit('the disposable browser test requires Chrome')
    with tempfile.TemporaryDirectory(prefix='enginex-browser-') as directory:
        runtime = Path(directory)
        Image.new('RGB', (1280, 800), '#101820').save(runtime / 'frame.png')
        session = str(uuid.uuid4())
        (runtime / 'engine.session').write_text(session)
        (runtime / 'frame.json').write_text(json.dumps({
            'width': 1280, 'height': 800, 'frame': 1,
            'renderer': 'opengl', 'stream': session,
        }))
        (runtime / 'setup.state').write_text('ready')
        packets = []
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as control:
            control.bind(str(runtime / 'control.sock'))
            control.settimeout(.2)
            stopped = threading.Event()

            def receive():
                while not stopped.is_set():
                    try:
                        packets.append(control.recv(256).decode())
                    except socket.timeout:
                        pass

            reader = threading.Thread(target=receive, daemon=True)
            reader.start()
            server = PreviewServer(('127.0.0.1', 8765), runtime, runtime)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                subprocess.run(['node', str(Path(__file__).with_name('test_touch_browser.mjs')),
                                chrome, directory], check=True, timeout=50)
                assert any(p.startswith('M 1 100.000 725.000 ') for p in packets), packets
                assert any(p.startswith('M 3 100.000 725.000 ') for p in packets), packets
                print('PASS real browser touch reached the preview input socket', flush=True)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=2)
                stopped.set()
                reader.join(timeout=2)


if __name__ == '__main__':
    main()
