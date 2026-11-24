//go:build ignore

// Runner-only fixture: no deck paths are accepted.
package main

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/Cd1s/EngineX-OS/pkg/mods"
)

var ids = []string{"output-equalizer", "subharmonic-synth", "prime4-steady-leds"}

func must(err error) {
	if err != nil {
		panic(err)
	}
}

func main() {
	if len(os.Args) < 3 {
		panic("usage: seed_prime4_gate seed|verify <ui> [three archives]")
	}
	ui, err := filepath.Abs(os.Args[2])
	must(err)
	if os.Getenv("RUNNER_TEMP") == "" {
		panic("RUNNER_TEMP is required")
	}
	temp, err := filepath.Abs(os.Getenv("RUNNER_TEMP"))
	must(err)
	rel, err := filepath.Rel(temp, ui)
	must(err)
	if os.Getenv("GITHUB_ACTIONS") != "true" || temp == "." || rel == "." || strings.HasPrefix(rel, "..") || filepath.Base(ui) != "ui" {
		panic("only a disposable GitHub runner fixture below RUNNER_TEMP is allowed")
	}
	media := filepath.Join(temp, "gate-fixture-media")
	must(os.MkdirAll(media, 0755))
	must(os.MkdirAll(ui, 0755))
	manager := mods.NewManager(media, ui)
	switch os.Args[1] {
	case "seed":
		if len(os.Args) != 6 {
			panic("three fixture archives required")
		}
		for i, path := range os.Args[3:] {
			f, err := os.Open(path)
			must(err)
			mod, err := manager.InstallArchive(f)
			must(f.Close())
			must(err)
			if mod.ID != ids[i] || !mod.Valid || mod.Enabled || mod.Script != "" {
				panic(fmt.Sprintf("invalid fixture Mod: %+v", mod))
			}
			must(manager.SetModEnabled(mod.ID, true))
		}
		// Non-flat, enabled test profiles must survive both boots unchanged.
		row := "1 0 1 10 56 25 100 100 -48 12 100 90 .707 -1 180 1 0 350 1 0 750 1 0 1500 1 0 3000 1 0 8000 1 0 19000 .707 0\n"
		must(os.WriteFile(filepath.Join(ui, "output-dsp-v1.conf"), []byte(strings.Repeat(row, 4)), 0644))
		must(os.WriteFile(filepath.Join(temp, "gate-profile.expected"), []byte(strings.Repeat(row, 4)), 0644))
		fmt.Println("PASS fixture: all three Mods installed disabled, then explicitly enabled")
	case "verify":
		list, err := manager.Discover()
		must(err)
		for _, id := range ids {
			found := false
			for _, mod := range list {
				if mod.ID != id {
					continue
				}
				if !mod.Valid || !mod.Enabled || mod.Quarantined || mod.Script != "" {
					panic(fmt.Sprintf("Mod did not survive boot: %+v", mod))
				}
				for src, dst := range mod.QMLFiles {
					want, err := os.ReadFile(filepath.Join(mod.Dir, src))
					must(err)
					got, err := os.ReadFile(filepath.Join(ui, "mods-overlay", dst))
					must(err)
					if !bytes.Equal(got, want) {
						panic("active QML differs: " + id + "/" + dst)
					}
				}
				found = true
			}
			if !found {
				panic("missing persisted Mod: " + id)
			}
		}
		want, err := os.ReadFile(filepath.Join(temp, "gate-profile.expected"))
		must(err)
		got, err := os.ReadFile(filepath.Join(ui, "output-dsp-v1.conf"))
		must(err)
		if !bytes.Equal(got, want) {
			panic("DSP profiles changed during boot")
		}
		fmt.Println("PASS fixture: enabled Mods, exact active QML and DSP profiles survived boot")
	default:
		panic("unsupported fixture operation")
	}
}
