"""End-to-end launcher check on a disposable CI host, never on a deck."""
import argparse
import json
from pathlib import Path
import subprocess
import shutil
import sys
import time
from urllib.request import Request, urlopen

# Only the disposable CI VM receives this non-default settings fixture. It is
# written by cloud-init, so subsequent boots/source upgrades must retain it.
SEEDED_LAUNCHER = r'''
import importlib.util,json,os,sys
if os.environ.get('GITHUB_ACTIONS')!='true': raise SystemExit('disposable CI host required')
path=sys.argv[1]
spec=importlib.util.spec_from_file_location('preview_launcher_under_test',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
original=module.cloud_config
def seeded(*args,**kwargs):
    config=json.loads(original(*args,**kwargs).split('\n',1)[1])
    row=[1,0,1,35,56,25,100,100,-48,12,100,90,.707,0,180,1,0,350,1,0,750,1,0,1500,1,0,3000,1,-3,8000,1,0,19000,.707,0]
    values=[]
    for i in range(4):
        profile=row.copy();profile[28]=-3-i;values.extend(profile)
    config['write_files'].append({'path':'/var/lib/enginex-preview/work/data/enginex/ui/output-dsp-v1.conf','content':' '.join(map(str,values))+'\n','permissions':'0644'})
    return '#cloud-config\n'+json.dumps(config)
module.cloud_config=seeded
sys.argv=[path,*sys.argv[2:]]
module.main()
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    parser.add_argument('--initial-launcher',type=Path,help='exercise an existing preview upgrade from an earlier checkout')
    args=parser.parse_args()
    args.directory.mkdir(parents=True,exist_ok=True)
    log=(args.directory/'launcher-test.log').open('w')
    command=[sys.executable,str(Path(__file__).with_name('launch.py')),'--directory',str(args.directory),'--no-browser']
    first_command=command.copy()
    if args.initial_launcher: first_command[1]=str(args.initial_launcher)
    first_command=[sys.executable,'-c',SEEDED_LAUNCHER,*first_command[1:]]
    process=subprocess.Popen(first_command,stdout=log,stderr=subprocess.STDOUT)

    def request(path,body=None):
        req=Request('http://127.0.0.1:8765'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=3) as response:
            return response.read()

    try:
        deadline=time.monotonic()+1200
        while time.monotonic()<deadline:
            if process.poll() is not None:
                raise RuntimeError('VM launcher exited early')
            console=args.directory/'console.log'
            if console.exists():
                tail=console.read_text(errors='replace')[-65536:]
                if 'Failed to run module scripts-user' in tail or 'no Skins/Embedded' in tail:
                    raise RuntimeError('VM setup failed; see the bounded serial diagnostics')
            try:
                status=json.loads(request('/api/status'))
                if status.get('setup')=='failed':
                    raise RuntimeError('guest preview setup failed')
                if status.get('engine')=='stopped':
                    raise RuntimeError('original Engine stopped before producing a framebuffer')
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
        chrome=shutil.which('google-chrome') or shutil.which('chromium')
        if not chrome:
            raise RuntimeError('the CI browser check needs the runner-provided Chrome browser')
        rendered=subprocess.run([chrome,'--headless','--no-sandbox','--disable-gpu',
            '--disable-background-networking','--disable-dev-shm-usage','--no-first-run',
            '--window-size=1600,1000','--virtual-time-budget=4000',
            '--screenshot='+str(args.directory/'browser-frame.png'),
            '--dump-dom','http://127.0.0.1:8765'],capture_output=True,text=True,timeout=40)
        if rendered.returncode or '/frame.png?frame=' not in rendered.stdout or 'Lokale Vorschau' not in rendered.stdout:
            raise RuntimeError('the real browser did not execute the preview frontend and load the Engine image')
        print('PASS real Chrome browser: frontend JavaScript, local status polling and original Engine image',flush=True)
        report=json.loads(request('/api/feedback',{'note':'isolated VM smoke test'}))
        assert report['uiOnly'] and len(report['sourceCommit'])==40
        assert [profile[28] for profile in report['dspProfiles']]==[-3,-4,-5,-6], 'non-default VM settings fixture missing'
        for action in ('down','up'):
            request('/api/input',{'kind':'pointer','action':action,'x':890,'y':68,'button':1,'buttons':int(action=='down')})
        # A new plugin instance replaces the UNIX socket and produces fresh frames.
        time.sleep(2)
        (args.directory/'navigation-frame.png').write_bytes(request('/frame.png'))
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
        next_command=command.copy()
        if args.initial_launcher: next_command.insert(2,'update')
        process=subprocess.Popen(next_command,stdout=log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+(600 if args.initial_launcher else 240)
        while time.monotonic()<deadline:
            if process.poll() is not None:
                raise RuntimeError('second VM boot exited early')
            try:
                status=json.loads(request('/api/status'))
                if status.get('setup')=='failed':
                    raise RuntimeError('updated preview setup failed')
                if status.get('engine')=='stopped':
                    raise RuntimeError('updated Engine stopped before producing a framebuffer')
                if status.get('frame',{}).get('width')==1280 and status['frame'].get('renderer')=='opengl':
                    break
            except OSError:
                pass
            time.sleep(2)
        else:
            raise RuntimeError('original Engine did not return after a full VM restart')
        restored=json.loads(request('/api/feedback',{'note':'second VM boot'}))
        assert restored['dspProfiles']==report['dspProfiles'], 'VM settings changed across reboot/update'
        if args.initial_launcher:
            assert restored['sourceCommit']!=report['sourceCommit'], 'the old source is still running after update'
            rendered=subprocess.run([chrome,'--headless','--no-sandbox','--disable-gpu',
                '--disable-background-networking','--disable-dev-shm-usage','--no-first-run',
                '--window-size=1600,1000','--virtual-time-budget=4000',
                '--screenshot='+str(args.directory/'browser-frame.png'),
                '--dump-dom','http://127.0.0.1:8765'],capture_output=True,text=True,timeout=40)
            assert rendered.returncode==0 and '/frame.png?frame=' in rendered.stdout
            print('PASS existing VM upgraded from the raster renderer to OpenGL with the same disk and DSP settings',flush=True)
        else:
            assert restored['sourceCommit']==report['sourceCommit']
        request('/api/stop',{})
        assert process.wait(timeout=90)==0, 'second VM shutdown failed'
        if args.initial_launcher:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+240
            while time.monotonic()<deadline:
                try:
                    status=json.loads(request('/api/status'))
                    if status.get('frame',{}).get('renderer')=='opengl': break
                except OSError: pass
                time.sleep(2)
            else: raise RuntimeError('upgraded VM did not survive a full shutdown and ordinary start')
            assert json.loads(request('/api/feedback',{}))['sourceCommit']==restored['sourceCommit']
            request('/api/stop',{})
            assert process.wait(timeout=90)==0
            print('PASS upgraded VM survived full shutdown and ordinary start',flush=True)
        print('PASS full local VM: first-install cloud-init, original Engine framebuffer, browser input endpoint, feedback, application restart, full guest shutdown and second boot')
    except BaseException:
        console=args.directory/'console.log'
        if console.exists():
            print('VM SERIAL BEFORE SHUTDOWN:\n'+console.read_text(errors='replace')[-24000:],flush=True)
        raise
    finally:
        if process.poll() is None:
            subprocess.run([*command,'stop'],check=False,timeout=10)
            try: process.wait(timeout=60)
            except subprocess.TimeoutExpired: pass
        log.close()


if __name__=='__main__': main()
