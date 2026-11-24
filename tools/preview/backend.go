//go:build ignore

// UI-only backend for the isolated desktop VM, never shipped to a deck.
package main

import (
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/Cd1s/EngineX-OS/pkg/mods"
	"github.com/Cd1s/EngineX-OS/pkg/resourceguard"
	"github.com/Cd1s/EngineX-OS/pkg/webui"
)

const runtimeDir = "/tmp/preview/dsp-simulation"

type localTransport struct{ base http.RoundTripper }

func (t localTransport) RoundTrip(r *http.Request) (*http.Response, error) {
	ip := net.ParseIP(r.URL.Hostname())
	if ip == nil || !ip.IsLoopback() {
		return nil, fmt.Errorf("desktop preview is offline")
	}
	return t.base.RoundTrip(r)
}

func must(err error) {
	if err != nil {
		log.Fatal(err)
	}
}

func capability() {
	boot, err := os.ReadFile("/proc/sys/kernel/random/boot_id")
	if err != nil {
		return
	}
	uptime, err := os.ReadFile("/proc/uptime")
	if err != nil {
		return
	}
	var now float64
	if _, err := fmt.Sscan(string(uptime), &now); err != nil || now < .02 {
		return
	}
	f, err := os.CreateTemp(runtimeDir, ".core-")
	if err != nil {
		return
	}
	defer os.Remove(f.Name())
	_, err = fmt.Fprintf(f, "OD1 %s %.3f 3 48000\n", strings.TrimSpace(string(boot)), now-.02)
	if closeErr := f.Close(); err == nil {
		err = closeErr
	}
	if err == nil {
		_ = os.Rename(f.Name(), filepath.Join(runtimeDir, "core.ready"))
	}
}

func main() {
	marker, err := os.ReadFile("/run/enginex-desktop-preview")
	if err != nil || string(marker) != "local-vm-only\n" {
		log.Fatal("desktop preview sandbox required")
	}
	const ui = "/data/enginex/ui"
	must(os.MkdirAll(ui, 0755))
	must(os.MkdirAll(runtimeDir, 0700))
	manager := mods.NewManager("/media", ui)
	list, err := manager.Discover()
	must(err)
	fresh := false
	if _, err := os.Stat("/data/enginex/.desktop-preview-init"); os.IsNotExist(err) {
		fresh = true
	}
	for _, bundle := range []struct{ id, version string }{
		{"output-equalizer", "0.1.1"}, {"subharmonic-synth", "0.1.1"}, {"prime4-steady-leds", "0.1.0"},
	} {
		id := bundle.id
		found := false
		upgrade := false
		for _, mod := range list {
			if mod.ID == id {
				found = true
				// The first preview seeded 0.1.0. Use the real Mod manager's
				// upgrade path so enabled state and saved profiles survive.
				upgrade = mod.Version == "0.1.0" && bundle.version == "0.1.1"
			}
		}
		if !found || upgrade {
			f, err := os.Open("/tmp/preview/mods/" + id + "-" + bundle.version + ".tar.gz")
			must(err)
			_, installErr := manager.InstallArchive(f)
			must(f.Close())
			must(installErr)
		}
		if fresh {
			must(manager.SetModEnabled(id, true))
		}
	}
	must(manager.ApplyActiveOverlay(""))
	must(os.WriteFile("/data/enginex/.desktop-preview-init", []byte("1\n"), 0644))
	capability()
	go func() {
		for range time.Tick(500 * time.Millisecond) {
			capability()
		}
	}()
	// An alternate runtime directory supplies UI capabilities. The real C hook
	// gets no native backend lease, so this does not activate audio processing.
	http.DefaultTransport = localTransport{http.DefaultTransport}
	guardCfg := resourceguard.DefaultConfig()
	guardCfg.Disabled = true
	jobs := webui.NewJobs(webui.Pipeline{Guard: resourceguard.New(guardCfg)})
	defer jobs.Close()
	server := webui.New(webui.Config{
		AccessToken: "desktop-preview-local", PublicURL: "http://127.0.0.1:8080",
		UIDir: ui, StateDir: "/data/enginex/state", OutputDSPRuntimeDir: runtimeDir,
		HTTP:          &http.Client{Transport: http.DefaultTransport, Timeout: 5 * time.Second},
		RestartEngine: func() error { return os.WriteFile("/tmp/preview/restart.request", []byte("restart\n"), 0600) },
	}, jobs)
	defer server.Close()
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "/update") || strings.Contains(r.URL.Path, "/factory") {
			http.Error(w, "unavailable in UI preview", http.StatusForbidden)
			return
		}
		server.ServeHTTP(w, r)
	})
	log.Fatal((&http.Server{Addr: "127.0.0.1:8080", Handler: handler, ReadHeaderTimeout: 5 * time.Second}).ListenAndServe())
}
