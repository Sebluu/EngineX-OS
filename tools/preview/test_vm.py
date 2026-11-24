"""End-to-end launcher check on a disposable CI host, never on a deck."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request, urlopen


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    args.directory.mkdir(parents=True,exist_ok=True)
    log=(args.directory/'launcher-test.log').open('w')
    command=[sys.executable,str(Path(__file__).with_name('launch.py')),'--directory',str(args.directory),'--no-browser']
    process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)

    def request(path,body=None):
        req=Request('http://127.0.0.1:8765'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=3) as response:
            return response.read()

    try:
        deadline=time.monotonic()+1200
        while time.monotonic()<deadline:
            if process.poll() is not None:
                raise RuntimeError('VM launcher exited early')
            try:
                status=json.loads(request('/api/status'))
                if status.get('frame',{}).get('width')==1280:
                    break
            except OSError:
                pass
            time.sleep(2)
        else:
            raise RuntimeError('VM preparation or Engine framebuffer timed out')
        image=request('/frame.png')
        assert image.startswith(b'\x89PNG\r\n\x1a\n') and len(image)>2000
        (args.directory/'browser-frame.png').write_bytes(image)
        report=json.loads(request('/api/feedback',{'note':'isolated VM smoke test'}))
        assert report['uiOnly'] and len(report['sourceCommit'])==40
        for action in ('down','up'):
            request('/api/input',{'kind':'pointer','action':action,'x':890,'y':68,'button':1,'buttons':int(action=='down')})
        # A new plugin instance replaces the UNIX socket and produces fresh frames.
        time.sleep(2)
        before=json.loads(request('/api/status'))['frame']['frame']
        request('/api/restart',{})
        deadline=time.monotonic()+180
        saw_reset=False
        while time.monotonic()<deadline:
            frame=json.loads(request('/api/status')).get('frame',{})
            if not frame or frame.get('frame',before)<before:
                saw_reset=True
            if saw_reset and frame.get('frame',0)>=2:
                break
            time.sleep(1)
        else:
            raise RuntimeError('Engine restart did not produce a fresh framebuffer')
        request('/api/stop',{})
        assert process.wait(timeout=90)==0, 'VM did not shut down cleanly'
        # Reuse the same disk and seed: the enabled service must start after a
        # real guest shutdown, without rerunning the first-install bootstrap.
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            if process.poll() is not None:
                raise RuntimeError('second VM boot exited early')
            try:
                status=json.loads(request('/api/status'))
                if status.get('frame',{}).get('width')==1280:
                    break
            except OSError:
                pass
            time.sleep(2)
        else:
            raise RuntimeError('original Engine did not return after a full VM restart')
        restored=json.loads(request('/api/feedback',{'note':'second VM boot'}))
        assert restored['sourceCommit']==report['sourceCommit']
        request('/api/stop',{})
        assert process.wait(timeout=90)==0, 'second VM shutdown failed'
        print('PASS full local VM: first-install cloud-init, original Engine framebuffer, browser input endpoint, feedback, application restart, full guest shutdown and second boot')
    finally:
        if process.poll() is None:
            subprocess.run([*command,'stop'],check=False,timeout=10)
            try: process.wait(timeout=60)
            except subprocess.TimeoutExpired: pass
        log.close()


if __name__=='__main__': main()
