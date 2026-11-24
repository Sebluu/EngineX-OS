#!/usr/bin/env python3
"""Start the local preview in a file-backed VM with no host device passthrough."""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import Request, urlopen
import webbrowser

ROOT = Path(__file__).resolve().parents[2]
BASE_URL = 'https://cloud-images.ubuntu.com/noble/20261017/noble-server-cloudimg-amd64.img'
BASE_SHA = '04e8f2461a16a44e78a370284471f29616cdd9baf1893df25807b71f985b6c94'
SOURCE_PATHS = ['go.mod', 'go.sum', 'cmd', 'internal', 'pkg', 'rootfs-overlay',
                'tools/az01-packer', 'tools/ui-mod', 'tools/mods', 'tools/preview', 'third_party',
                'docs/mods/src', 'docs/assets/boot-splash-enginex.png']

def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()

def cloud_config(archive, commit, port=8765):
    unit = '''[Unit]
Description=Local EngineX UI preview
Wants=network-online.target
After=network-online.target
[Service]
Type=simple
ExecStart=/bin/bash /opt/enginex-preview-source/tools/preview/guest-start.sh
TimeoutStopSec=30
[Install]
WantedBy=multi-user.target
'''
    bootstrap = '''#!/bin/bash
set -euo pipefail
cd /var/lib/enginex-preview
sha256sum -c source.sha256
mkdir -p /opt/enginex-preview-source
tar --no-same-owner -xzf source.tar.gz -C /opt/enginex-preview-source
cp source.commit /opt/enginex-preview-source/.preview-source-sha
bash /opt/enginex-preview-source/tools/preview/guest-prepare.sh
systemctl daemon-reload
systemctl enable enginex-preview.service
systemctl start --no-block enginex-preview.service
'''
    entries = [
        {'path':'/var/lib/enginex-preview/source.tar.gz','encoding':'b64','permissions':'0600','content':base64.b64encode(archive).decode()},
        {'path':'/var/lib/enginex-preview/source.sha256','content':hashlib.sha256(archive).hexdigest()+'  source.tar.gz\n'},
        {'path':'/var/lib/enginex-preview/source.commit','content':commit+'\n'},
        {'path':'/etc/enginex-preview-port','content':str(port)+'\n'},
        {'path':'/var/lib/enginex-preview/bootstrap.sh','permissions':'0700','content':bootstrap},
        {'path':'/etc/systemd/system/enginex-preview.service','content':unit},
    ]
    return '#cloud-config\n'+json.dumps({
        'package_update':True,
        'packages':['build-essential','g++-arm-linux-gnueabihf','libc6-dev-armhf-cross',
                    'qt6-base-dev-tools','qemu-user','qemu-user-static','binfmt-support','e2fsprogs',
                    'zstd','python3-pil','iproute2','curl','git','golang-go','xz-utils'],
        'write_files':entries,
        'runcmd':[['bash','/var/lib/enginex-preview/bootstrap.sh']],
        'ssh_pwauth':False,
    },ensure_ascii=False)

def qemu_command(directory, port, memory, cpus, accel):
    d = Path(directory)
    if accel == 'auto': accel = 'kvm' if os.access('/dev/kvm', os.R_OK|os.W_OK) else 'tcg'
    return ['qemu-system-x86_64','-name','EngineX local preview','-machine','q35',
            '-accel',accel if accel=='kvm' else 'tcg,thread=multi',
            '-cpu','host' if accel=='kvm' else 'max','-m',str(memory),'-smp',str(cpus),
            '-nodefaults','-display','none','-monitor','none','-no-reboot',
            '-serial','file:'+str(d/'console.log'),
            '-qmp','unix:'+str(d/'qmp.sock')+',server=on,wait=off',
            '-drive','file='+str(d/'preview.qcow2')+',format=qcow2,if=virtio,index=0',
            '-drive','file='+str(d/'seed.img')+',format=raw,if=virtio,index=1,readonly=on',
            '-device','virtio-rng-pci',
            '-netdev',f'user,id=previewnet,hostfwd=tcp:127.0.0.1:{port}-:8765',
            '-device','virtio-net-pci,netdev=previewnet']

def qmp_powerdown(directory):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(3)
        client.connect(str(Path(directory)/'qmp.sock'))
        stream = client.makefile('rwb')
        stream.readline()
        for command in ('qmp_capabilities','system_powerdown'):
            stream.write((json.dumps({'execute':command})+'\n').encode()); stream.flush()
            stream.readline()

def stop_vm(directory, port):
    try:
        request=Request(f'http://127.0.0.1:{port}/api/stop',data=b'{}',headers={'Content-Type':'application/json'})
        with urlopen(request,timeout=3): return
    except OSError:
        qmp_powerdown(directory)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',nargs='?',choices=('start','stop','logs'),default='start')
    parser.add_argument('--directory',type=Path,default=Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'enginex-preview')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--memory',type=int,default=4096)
    parser.add_argument('--cpus',type=int,default=4)
    parser.add_argument('--accel',choices=('auto','kvm','tcg'),default='auto')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    directory=args.directory.expanduser().resolve()
    if directory == Path('/') or any(directory.is_relative_to(Path(p)) for p in ('/dev','/sys','/proc')):
        parser.error('use a private directory for VM files')
    if not 1024 <= args.port <= 65535 or not 2048 <= args.memory <= 16384 or not 1 <= args.cpus <= 16:
        parser.error('invalid VM resources or port')
    if args.action=='logs':
        path=directory/'console.log'
        print(path.read_text(errors='replace')[-16000:] if path.exists() else 'Noch kein VM-Protokoll vorhanden.');return
    if args.action=='stop':
        stop_vm(directory,args.port); print('Herunterfahren der lokalen VM angefordert.');return
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        parser.error('this launcher currently supports Linux x86_64')
    missing=[name for name in ('qemu-system-x86_64','qemu-img','cloud-localds','git') if not shutil.which(name)]
    if missing:
        parser.exit(2,'Einmalig die lokalen VM-Werkzeuge installieren:\n  sudo apt install qemu-system-x86 qemu-utils cloud-image-utils git\n')
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock=(directory/'launcher.lock').open('a')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: parser.exit(2,f'Die Vorschau läuft bereits: http://127.0.0.1:{args.port}\n')
    try:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            probe.bind(('127.0.0.1',args.port))
    except OSError: parser.exit(2,'Der Browser-Port ist bereits belegt. Wähle einen anderen mit --port.\n')
    base=directory/'ubuntu-noble-20261017.qcow2'
    if not base.exists():
        print('Lade die Basis für die lokale VM herunter …',flush=True)
        temporary=base.with_suffix('.download')
        with urlopen(BASE_URL,timeout=60) as source, temporary.open('wb') as target:
            shutil.copyfileobj(source,target)
        if digest(temporary)!=BASE_SHA:
            temporary.unlink();parser.exit(1,'Die Ubuntu-Prüfsumme stimmt nicht.\n')
        temporary.rename(base)
    elif digest(base)!=BASE_SHA:
        parser.exit(1,'Die zwischengespeicherte Ubuntu-Basis wurde verändert.\n')
    disk=directory/'preview.qcow2'
    if not disk.exists():
        subprocess.run(['qemu-img','create','-f','qcow2','-F','qcow2','-b',str(base),str(disk),'24G'],check=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    identity={'commit':commit,'port':args.port}
    pin=directory/'preview.json'
    if pin.exists() and json.loads(pin.read_text()) != identity:
        parser.exit(2,'Diese VM gehört zu einem anderen Quellstand oder Port. Starte die neue Vorschau mit einem frischen --directory.\n')
    archive=subprocess.check_output(['git','archive','--format=tar.gz','HEAD','--',*SOURCE_PATHS],cwd=ROOT)
    if len(archive)>64*1024*1024: parser.exit(1,'Der Vorschau-Quellstand ist unerwartet groß.\n')
    (directory/'user-data').write_text(cloud_config(archive,commit,args.port))
    (directory/'meta-data').write_text(json.dumps({'instance-id':'enginex-preview-'+commit,'local-hostname':'enginex-preview'}))
    subprocess.run(['cloud-localds',str(directory/'seed.img'),str(directory/'user-data'),str(directory/'meta-data')],check=True)
    pin.write_text(json.dumps(identity))
    command=qemu_command(directory,args.port,args.memory,args.cpus,args.accel)
    print(f'Lokale VM startet. Beim ersten Start werden Firmware und Werkzeuge vorbereitet.\nBrowser: http://127.0.0.1:{args.port}\nStoppen: Strg+C',flush=True)
    if 'tcg,thread=multi' in command: print('Softwareemulation aktiv; der erste Start kann deutlich länger dauern.',flush=True)
    process=subprocess.Popen(command,start_new_session=True)
    try:
        opened=False
        while process.poll() is None:
            if not opened:
                try:
                    with urlopen(f'http://127.0.0.1:{args.port}/api/status',timeout=1) as response:
                        if response.status==200:
                            opened=True
                            if not args.no_browser: webbrowser.open(f'http://127.0.0.1:{args.port}')
                except OSError: pass
            time.sleep(1)
        if process.returncode: parser.exit(1,'Die VM wurde beendet. Details: python3 tools/preview/launch.py logs\n')
    except KeyboardInterrupt:
        print('\nDie lokale VM wird heruntergefahren …',flush=True)
        stop_vm(directory,args.port)
        try: process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            print('Die VM fährt noch herunter. Bitte nicht die Datendateien löschen.',file=sys.stderr)

if __name__=='__main__': main()
