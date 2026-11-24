package webui

import (
    "bytes"
    "encoding/json"
    "fmt"
    "math"
    "net/http/httptest"
    "os"
    "os/exec"
    "path/filepath"
    "testing"
)

func odTestServer(t *testing.T) *Server {
    t.Helper()
    s:=&Server{cfg:Config{UIDir:t.TempDir(),MediaRoot:t.TempDir(),OutputDSPRuntimeDir:t.TempDir()}}
    previous:=deviceCompatiblePath
    deviceCompatiblePath=filepath.Join(t.TempDir(),"compatible")
    if err:=os.WriteFile(deviceCompatiblePath,[]byte("inmusic,jc11\x00"),0600);err!=nil{t.Fatal(err)}
    t.Cleanup(func(){deviceCompatiblePath=previous})
    return s
}
func odTestReady(t *testing.T,s *Server) {
    t.Helper();boot,now,err:=odBoot();if err!=nil{t.Fatal(err)}
    if err=os.WriteFile(filepath.Join(s.odRuntime(),"core.ready"),[]byte(fmt.Sprintf("OD1 %s %.3f 3 48000\n",boot,now)),0600);err!=nil{t.Fatal(err)}
}
func odRequest(s *Server,method,body string) *httptest.ResponseRecorder {
    r:=httptest.NewRequest(method,"http://127.0.0.1:8080/v1/enginex/output-dsp",bytes.NewBufferString(body));r.RemoteAddr="127.0.0.1:4444";r.Header.Set("Content-Type","application/json")
    w:=httptest.NewRecorder();s.handleOutputDSP(w,r);return w
}
func TestOutputDSPValidationAndPersistence(t *testing.T) {
    defaults:=odDefaults();for _,row:=range defaults{if !odValid(row)||row[0]!=0||row[2]!=0{t.Fatal("unsafe defaults")}}
    for _,bad:=range []float64{math.NaN(),math.Inf(1),math.Inf(-1),-1000,1000000} {row:=defaults[0];row[9]=bad;if odValid(row){t.Fatal("invalid attack accepted")}}
    path:=filepath.Join(t.TempDir(),"dsp.conf");defaults[3][34]=-6
    if err:=odSave(path,defaults);err!=nil{t.Fatal(err)}
    if odRead(path)!=defaults{t.Fatal("settings did not survive reopening")}
    for _,data:=range []string{"nan 1\n","truncated","","1 2 3"} {if err:=os.WriteFile(path,[]byte(data),0600);err!=nil{t.Fatal(err)};if odRead(path)!=odDefaults(){t.Fatal("corrupt config did not disable DSP")}}
}
func TestOutputDSPModArchiveLifecycle(t *testing.T) {
    s:=odTestServer(t);out:=t.TempDir()
    cmd:=exec.Command("python3","../../tools/mods/build_output_dsp_mods.py","--out",out)
    if data,err:=cmd.CombinedOutput();err!=nil{t.Fatalf("mod builder: %s %v",data,err)}
    mgr:=s.modsManager()
    for _,id:=range []string{"output-equalizer","subharmonic-synth"} {
        f,err:=os.Open(filepath.Join(out,id+"-0.1.0.tar.gz"));if err!=nil{t.Fatal(err)}
        mod,err:=mgr.InstallArchive(f);f.Close();if err!=nil{t.Fatal(err)}
        if mod.Enabled||!mod.Valid||mod.Script!=""{t.Fatal("archive must install valid, inert and disabled")}
        if err=mgr.SetModEnabled(id,true);err!=nil{t.Fatal(err)}
    }
    odTestReady(t,s)
    if s.odEnabled()!=3{t.Fatal("enabled Mods missing")}
    row:=odDefaults()[0];row[0]=1;row[2]=1;row[28]=-6
    body,_:=json.Marshal(map[string]any{"section":"eq","pair":0,"values":row})
    if w:=odRequest(s,"POST",string(body));w.Code!=200{t.Fatalf("EQ: %d %s",w.Code,w.Body.String())}
    table:=odRead(filepath.Join(s.uiDir(),"output-dsp-v1.conf"));if table[0][0]!=1||table[0][2]!=0{t.Fatal("EQ request changed SUB")}
    if err:=s.odRefreshLease();err!=nil{t.Fatal(err)}
    boot,now,_:=odBoot();mask,_:=odReadRecord(filepath.Join(s.odRuntime(),"backend.lease"),boot,now);if mask!=3{t.Fatal("no lease")}
    if mask,_=odReadRecord(filepath.Join(s.odRuntime(),"backend.lease"),"different-boot",now);mask!=0{t.Fatal("reboot reused old lease")}
    if mask,_=odReadRecord(filepath.Join(s.odRuntime(),"backend.lease"),boot,now+4);mask!=0{t.Fatal("dead backend lease did not expire")}
    if err:=mgr.SetModEnabled("output-equalizer",false);err!=nil{t.Fatal(err)}
    if s.odEnabled()!=2{t.Fatal("disable ignored")}
    if w:=odRequest(s,"POST",string(body));w.Code!=409{t.Fatal("disabled EQ accepted edits")}
    if err:=mgr.QuarantineAll();err!=nil{t.Fatal(err)}
    if s.odEnabled()!=0{t.Fatal("quarantine ignored")}
    if err:=s.odRefreshLease();err!=nil{t.Fatal(err)}
    boot,now,_=odBoot();if mask,_=odReadRecord(filepath.Join(s.odRuntime(),"backend.lease"),boot,now);mask!=0{t.Fatal("quarantine renewed processing")}
    if err:=mgr.UninstallMod("output-equalizer");err!=nil{t.Fatal(err)}
    if table!=odRead(filepath.Join(s.uiDir(),"output-dsp-v1.conf")){t.Fatal("uninstall destroyed settings")}
}
func TestOutputDSPRefusesUnsupportedOrUnavailable(t *testing.T) {
    s:=odTestServer(t)
    if mask,_:=s.odAvailable();mask!=0{t.Fatal("stock firmware claimed native DSP")}
    if err:=os.WriteFile(deviceCompatiblePath,[]byte("inmusic,jc11s\x00"),0600);err!=nil{t.Fatal(err)}
    if w:=odRequest(s,"GET","");w.Code!=404{t.Fatal("PRIME 4+ must be excluded")}
    if err:=os.WriteFile(deviceCompatiblePath,[]byte("inmusic,jc11\x00"),0600);err!=nil{t.Fatal(err)}
    r:=httptest.NewRequest("GET","http://127.0.0.1:8080/v1/enginex/output-dsp",nil);r.RemoteAddr="192.168.1.9:4000"
    w:=httptest.NewRecorder();s.handleOutputDSP(w,r);if w.Code!=403{t.Fatal("LAN edit allowed")}
}
