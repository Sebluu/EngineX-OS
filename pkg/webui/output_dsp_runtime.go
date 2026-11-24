package webui

import (
    "errors"
    "fmt"
    "io"
    "math"
    "os"
    "path/filepath"
    "strings"
    "syscall"
    "time"
)

func (s *Server) odRuntime() string {
    if s.cfg.OutputDSPRuntimeDir!="" { return s.cfg.OutputDSPRuntimeDir }
    return "/tmp/enginex-output-dsp"
}

func odBoot() (string,float64,error) {
    id,err:=os.ReadFile("/proc/sys/kernel/random/boot_id");if err!=nil{return "",0,err}
    boot:=strings.TrimSpace(string(id));if len(boot)!=36{return "",0,errors.New("invalid boot identity")}
    data,err:=os.ReadFile("/proc/uptime");if err!=nil{return "",0,err}
    var uptime float64
    if _,err=fmt.Sscan(string(data),&uptime);err!=nil||!isODTime(uptime){return "",0,errors.New("invalid uptime")}
    return boot,uptime,nil
}
func isODTime(v float64) bool { return !math.IsNaN(v)&&!math.IsInf(v,0)&&v>=0 }

// The same record is parsed by output_dsp_control.h. CLOCK_BOOTTIME and
// /proc/uptime share a clock, including suspend; wall-clock changes are irrelevant.
func odReadRecord(path,boot string,now float64) (uint,uint) {
    f,err:=os.OpenFile(path,os.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK,0);if err!=nil{return 0,0};defer f.Close()
    st,err:=f.Stat();if err!=nil||!st.Mode().IsRegular()||st.Size()<=0||st.Size()>=160{return 0,0}
    var magic,id,extra string;var then float64;var mask,rate uint
    if n,e:=fmt.Fscan(f,&magic,&id,&then,&mask,&rate);e!=nil||n!=5||magic!="OD1"||id!=boot||!isODTime(then)||then>now||now-then>3||mask>3{return 0,0}
    if _,err=fmt.Fscan(f,&extra);err!=io.EOF{return 0,0}
    return mask,rate
}
func (s *Server) odAvailable() (uint,uint) {
    boot,now,err:=odBoot();if err!=nil{return 0,0}
    mask,rate:=odReadRecord(filepath.Join(s.odRuntime(),"core.ready"),boot,now)
    if rate<32000||rate>192000{return 0,0}
    return mask,rate
}
func (s *Server) odRefreshLease() error {
    path:=filepath.Join(s.odRuntime(),"backend.lease")
    boot,now,err:=odBoot();if err!=nil{_ = os.Remove(path);return err}
    // Slow or failed discovery cannot extend a stale heartbeat.
    mask:=s.odEnabled()
    if err=os.MkdirAll(s.odRuntime(),0700);err!=nil{return err}
    f,err:=os.CreateTemp(s.odRuntime(),".backend-");if err!=nil{return err}
    defer os.Remove(f.Name());defer f.Close()
    if _,err=fmt.Fprintf(f,"OD1 %s %.3f %d 0\n",boot,now,mask);err!=nil{return err}
    if err=f.Close();err!=nil{return err}
    return os.Rename(f.Name(),path)
}
func (s *Server) odLeaseLoop() {
    tick:=time.NewTicker(time.Second);defer tick.Stop()
    defer os.Remove(filepath.Join(s.odRuntime(),"backend.lease"))
    for {
        select {case <-s.closed:return;default:}
        _ = s.odRefreshLease()
        select {case <-s.closed:return;case <-tick.C:}
    }
}
