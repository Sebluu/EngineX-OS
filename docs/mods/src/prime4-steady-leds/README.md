# PRIME 4 Steady LEDs 0.1.0 (experimental)

QML-only Mod for the original PRIME 4 / JC11 on the pinned Engine OS 5.3.0
resources. No DSP core, helper binary, script, firmware edit, MIDI-note rewrite,
MCU update or system service is needed.

The official JC11 assignment identifies itself as "PRIME 4 Controller
Assignment". The two shared QML modules check that exact creation context;
other assignment contexts retain their original LED expressions.

- DJ-FX ON LEDs stay continuously on while the corresponding FX is active.
  Inactive LEDs retain the vendor's inactive state.
- Simple PLAY LEDs are on only while the deck or playlist deck is playing.
  Pause, end and empty decks are off. Bluetooth follows its own play state;
  Line In stays off. The native Computer Mode suppression is preserved.
- CUE LEDs, transport actions, beat synchronization, note/channel routing,
  deck/layer selection, RGB PLAY LEDs and all audio code remain unchanged.

QML assignment components load with Engine. Enable, disable or remove the Mod
through Mod Hub, then perform an explicit Engine UI restart when playback has
stopped. No automatic restart is performed. The standard Mod loader owns
restoration and quarantine; a clean restart reloads the selected overlay.

Build off-device with tools/mods/build_prime4_led_mod.py and matching extracted
--rootfs / --qrc fixtures. The builder refuses unknown hashes or a non-unique
controller scope. Vendor resources are read locally and never committed to
this repository. Generated archives are deterministic and have provenance
and checksum metadata. This source is experimental and not approved for deck
installation: actual controller-QML startup, restart/fallback and physical
LED behavior still require validation. No runtime test touches a real deck.
