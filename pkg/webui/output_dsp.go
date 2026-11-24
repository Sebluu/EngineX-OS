package webui

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"math"
	"mime"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"syscall"
)

var odMu sync.Mutex

type odRow [35]float64
type odTable [4]odRow

func odDefaults() odTable {
	var t odTable
	for i := range t {
		t[i] = odRow{0, 0, 0, 25, 56, 25, 100, 100, -48, 12, 100, 90, .707, 0, 180, 1, 0, 350, 1, 0, 750, 1, 0, 1500, 1, 0, 3000, 1, 0, 8000, 1, 0, 19000, .707, 0}
	}
	return t
}
func odValid(v odRow) bool {
	limits := [][2]float64{{0, 1}, {0, 150}, {0, 1}, {0, 100}, {30, 80}, {15, 55}, {0, 100}, {0, 100}, {-80, -12}, {2, 100}, {20, 500}}
	valid := func(x, lo, hi float64) bool { return !math.IsNaN(x) && !math.IsInf(x, 0) && x >= lo && x <= hi }
	for i, l := range limits {
		if !valid(v[i], l[0], l[1]) {
			return false
		}
	}
	if (v[0] != 0 && v[0] != 1) || (v[2] != 0 && v[2] != 1) || (v[1] > 0 && v[1] < 10) || v[4] < v[5]+5 {
		return false
	}
	for i := 11; i < 35; i += 3 {
		if !valid(v[i], 20, 22000) || !valid(v[i+1], .3, 8) || !valid(v[i+2], -12, 12) {
			return false
		}
	}
	return true
}
func odRead(path string) odTable {
	f, e := os.OpenFile(path, os.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0)
	if e != nil {
		return odDefaults()
	}
	defer f.Close()
	st, e := f.Stat()
	if e != nil || !st.Mode().IsRegular() || st.Size() > 8192 {
		return odDefaults()
	}
	r := bufio.NewReader(f)
	var t odTable
	for i := range t {
		for j := range t[i] {
			if _, e = fmt.Fscan(r, &t[i][j]); e != nil {
				return odDefaults()
			}
		}
		if !odValid(t[i]) {
			return odDefaults()
		}
	}
	var extra string
	if _, e = fmt.Fscan(r, &extra); e != io.EOF {
		return odDefaults()
	}
	return t
}
func odSave(path string, t odTable) error {
	if e := os.MkdirAll(filepath.Dir(path), 0755); e != nil {
		return e
	}
	f, e := os.CreateTemp(filepath.Dir(path), ".output-dsp-")
	if e != nil {
		return e
	}
	defer os.Remove(f.Name())
	defer f.Close()
	for _, v := range t {
		for _, n := range v {
			if _, e = fmt.Fprintf(f, "%.8g ", n); e != nil {
				return e
			}
		}
		if _, e = fmt.Fprintln(f); e != nil {
			return e
		}
	}
	if e = f.Chmod(0644); e != nil {
		return e
	}
	if e = f.Sync(); e != nil {
		return e
	}
	if e = f.Close(); e != nil {
		return e
	}
	if e = os.Rename(f.Name(), path); e != nil {
		return e
	}
	d, e := os.Open(filepath.Dir(path))
	if e != nil {
		return e
	}
	defer d.Close()
	return d.Sync()
}
func odLoopback(addr string) bool {
	h, _, e := net.SplitHostPort(addr)
	if e != nil {
		h = addr
	}
	ip := net.ParseIP(h)
	return ip != nil && ip.IsLoopback()
}

// odEnabled requires the Mod loader's full validation, including removable-drive
// identity and quarantine. A saved enabled bit alone is not authorization.
func (s *Server) odEnabled() uint {
	list, err := s.modsManager().Discover()
	if err != nil {
		return 0
	}
	var mask uint
	for _, mod := range list {
		if !mod.Valid || !mod.Enabled || mod.Quarantined {
			continue
		}
		switch mod.ID {
		case "output-equalizer":
			mask |= 1
		case "subharmonic-synth":
			mask |= 2
		}
	}
	return mask
}

func (s *Server) handleOutputDSP(w http.ResponseWriter, r *http.Request) {
	if !odLoopback(r.RemoteAddr) || !odLoopback(r.Host) {
		fail(w, 403, errors.New("deck-local only"))
		return
	}
	if imagePrefix(deviceCompatible()) != "PRIME4" {
		fail(w, 404, errors.New("unsupported model"))
		return
	}
	if r.Method != http.MethodGet && r.Method != http.MethodPost {
		fail(w, 405, errors.New("method not allowed"))
		return
	}
	odMu.Lock()
	defer odMu.Unlock()
	path := filepath.Join(s.uiDir(), "output-dsp-v1.conf")
	t := odRead(path)
	available, rate := s.odAvailable()
	enabled := s.odEnabled() & available
	if r.Method == http.MethodPost {
		media, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
		if err != nil || media != "application/json" {
			fail(w, 415, errors.New("application/json required"))
			return
		}
		if origin := r.Header.Get("Origin"); origin != "" && origin != "http://"+r.Host {
			fail(w, 403, errors.New("invalid origin"))
			return
		}
		var req struct {
			Pair    int       `json:"pair"`
			Values  []float64 `json:"values"`
			Toggle  bool      `json:"toggle"`
			Section string    `json:"section"`
		}
		if !input(w, r, &req) {
			return
		}
		if req.Pair < 0 || req.Pair >= 4 || (req.Section != "eq" && req.Section != "sub") {
			fail(w, 400, errors.New("invalid output or section"))
			return
		}
		bit := uint(1)
		if req.Section == "sub" {
			bit = 2
		}
		if enabled&bit == 0 {
			fail(w, 409, errors.New("matching native core and enabled Mod required"))
			return
		}
		q := t[req.Pair]
		if req.Toggle && req.Section == "sub" && req.Pair == 0 && len(req.Values) == 0 {
			q[2] = 1 - q[2]
		} else {
			if len(req.Values) != 35 || req.Toggle {
				fail(w, 400, errors.New("expected 35 values"))
				return
			}
			if req.Section == "eq" {
				copy(q[:2], req.Values[:2])
				copy(q[11:], req.Values[11:])
			} else {
				copy(q[2:11], req.Values[2:11])
			}
		}
		if !odValid(q) {
			fail(w, 400, errors.New("invalid DSP values"))
			return
		}
		t[req.Pair] = q
		if e := odSave(path, t); e != nil {
			fail(w, 500, e)
			return
		}
	}
	w.Header().Set("Cache-Control", "no-store")
	respond(w, map[string]any{"version": 1, "available": available, "enabled": enabled, "rate": rate, "profiles": t})
}
