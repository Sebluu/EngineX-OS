//go:build ignore

// This checker uses temporary directories only, on the build runner.
package main

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/Cd1s/EngineX-OS/pkg/mods"
)

func main() {
	work, err := os.MkdirTemp("", "jc11-led-loader-")
	if err != nil {
		panic(err)
	}
	defer os.RemoveAll(work)
	ui := filepath.Join(work, "ui")
	media := filepath.Join(work, "media")
	for _, dir := range []string{ui, media} {
		if err := os.MkdirAll(dir, 0755); err != nil {
			panic(err)
		}
	}
	manager := mods.NewManager(media, ui)
	archive, err := os.Open(os.Args[1])
	if err != nil {
		panic(err)
	}
	mod, err := manager.InstallArchive(archive)
	archive.Close()
	if err != nil || !mod.Valid || mod.Enabled || mod.Script != "" {
		panic(fmt.Sprintf("invalid initial Mod state: %+v %v", mod, err))
	}
	id := "prime4-steady-leds"
	if err := manager.SetModEnabled(id, true); err != nil {
		panic(err)
	}
	restarted := mods.NewManager(media, ui)
	if !restarted.IsModEnabled(id) {
		panic("enabled state did not survive loader reconstruction")
	}
	if err := restarted.SetModEnabled(id, false); err != nil {
		panic(err)
	}
	if restarted.IsModEnabled(id) {
		panic("disable ignored")
	}
	if err := restarted.SetModEnabled(id, true); err != nil {
		panic(err)
	}
	if err := restarted.QuarantineAll(); err != nil {
		panic(err)
	}
	if restarted.IsModEnabled(id) {
		panic("quarantine ignored")
	}
	if err := restarted.UninstallMod(id); err != nil {
		panic(err)
	}
	if restarted.IsModEnabled(id) {
		panic("uninstall ignored")
	}
	fmt.Println("PASS JC11 LED archive: disabled install, enable, loader restart, disable, quarantine, uninstall")
}
