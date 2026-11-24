"""Preview boundaries: real HTTP checks and launcher output, without a deck."""
import base64
import http.client
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

import launch
import server


class LauncherTests(unittest.TestCase):
    def test_vm_exposes_only_loopback_and_generated_disks(self):
        command = launch.qemu_command('/tmp/preview-test', 8765, 4096, 4, 'tcg')
        joined = ' '.join(command)
        for unsafe in ('/dev/sd', '/dev/nvme', 'usb-host', 'vfio', 'virtfs', '-fsdev', 'audiodev', 'vnc', '0.0.0.0'):
            self.assertNotIn(unsafe, joined)
        self.assertIn('user,id=previewnet,hostfwd=tcp:127.0.0.1:8765-:8765', command)
        self.assertEqual(command.count('-drive'), 2)
        self.assertIn('-nodefaults', command)
        self.assertIn('-display', command)

    def test_cloud_init_embeds_reviewed_source_without_credentials(self):
        source = b'fixture source archive'
        config = json.loads(launch.cloud_config(source, 'a'*40, 9001).split('\n', 1)[1])
        files = {item['path']: item for item in config['write_files']}
        embedded = files['/var/lib/enginex-preview/source.tar.gz']['content']
        self.assertEqual(base64.b64decode(embedded), source)
        self.assertEqual(files['/etc/enginex-preview-port']['content'], '9001\n')
        self.assertIn(launch.hashlib.sha256(source).hexdigest(), files['/var/lib/enginex-preview/source.sha256']['content'])
        self.assertNotIn('ssh_authorized_keys', config)
        self.assertFalse(config['ssh_pwauth'])
        self.assertIn('tools', launch.SOURCE_PATHS)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = self.root/'runtime'; self.runtime.mkdir()
        self.data = self.root/'data'; (self.data/'enginex/ui').mkdir(parents=True)
        (self.runtime/'frame.json').write_text(json.dumps({'width':1280,'height':800,'frame':1,'renderer':'software','secret':'never-export'}))
        (self.runtime/'build.json').write_text(json.dumps({'sourceCommit':'a'*40,'token':'never-export'}))
        self.http = server.PreviewServer(('127.0.0.1',0), self.runtime, self.data)
        self.thread = threading.Thread(target=self.http.serve_forever,daemon=True); self.thread.start()
        self.port = self.http.server_address[1]

    def tearDown(self):
        self.http.shutdown(); self.http.server_close(); self.thread.join(); self.temp.cleanup()

    def request(self,path,body=None,headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        conn.request('POST' if body is not None else 'GET',path,body=json.dumps(body) if body is not None else None,headers=headers or {})
        response=conn.getresponse(); result=(response.status,response.read(),dict(response.getheaders()));conn.close();return result

    def test_real_http_input_reaches_unix_socket(self):
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as control:
            control.bind(str(self.runtime/'control.sock')); control.settimeout(1)
            code,_,_=self.request('/api/input',{'kind':'pointer','action':'down','x':42,'y':67,'button':1,'buttons':1})
            self.assertEqual(code,200)
            self.assertEqual(control.recv(256),b'M 1 42.000 67.000 1 1 0')

    def test_cross_site_and_foreign_hosts_cannot_send_events(self):
        for headers in ({'Origin':'https://example.org'}, {'Host':'example.org'}, {'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.request('/api/restart',{},headers)[0],403)
        self.assertFalse((self.runtime/'restart.request').exists())

    def test_invalid_input_is_rejected(self):
        for field,value in (('x',-1),('y',800),('x',float('nan')),('buttons',99),('mods',-1)):
            body={'kind':'pointer','action':'down','x':2,'y':3,'button':1,'buttons':1}
            body[field]=value
            self.assertEqual(self.request('/api/input',body)[0],400)
        for body in ({'kind':'key','action':'down','key':True},{'kind':'key','action':'down','key':65,'text':0xd800}):
            self.assertEqual(self.request('/api/input',body)[0],400)

    def test_feedback_is_explicitly_limited_and_local(self):
        (self.data/'StreamingAccounts.json').write_text('{"token":"never-export"}')
        (self.data/'enginex/ui/output-dsp-v1.conf').write_text(' '.join(['0']*140))
        code,raw,headers=self.request('/api/feedback',{'note':'my test'})
        result=json.loads(raw)
        self.assertEqual(code,200); self.assertTrue(result['uiOnly'])
        self.assertEqual(result['note'],'my test');self.assertEqual(len(result['dspProfiles']),4)
        self.assertNotIn('never-export',raw.decode())
        self.assertIn("connect-src 'self'",headers['Content-Security-Policy'])
        self.assertEqual(self.request('/api/feedback',{'note':42})[0],400)

    def test_restart_is_a_local_request_and_stop_requires_vm(self):
        self.assertEqual(self.request('/api/restart',{})[0],200)
        self.assertEqual((self.runtime/'restart.request').read_text(),'restart\n')
        with patch.object(server,'inside_vm',return_value=False), patch.object(server.subprocess,'run') as command:
            self.assertEqual(self.request('/api/stop',{})[0],403)
            command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
