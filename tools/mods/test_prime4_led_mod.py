import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import build_prime4_led_mod as led

class Prime4LEDBuilder(unittest.TestCase):
    def test_unknown_vendor_source_is_refused(self):
        with self.assertRaises(ValueError):
            led.transform("PlayCue.qml", b"Item {}")

    def test_only_play_led_binding_is_changed(self):
        raw = b'''Item {
    id: module
    property int cueValue: 123
    OutputAssignment {
        objectName: "Play LED Deck%1".arg(deckConfig.name)
        enabled: !deckConfig.inComputerMode
        readonly property int ledValue: { deckConfig.tempoSyncedFlashState ? 127 : 0 }
    }
}
'''
        with patch.dict(led.HASHES, {"PlayCue.qml": hashlib.sha256(raw).hexdigest()}):
            result = led.transform("PlayCue.qml", raw).decode()
        self.assertIn("property int cueValue: 123", result)
        self.assertIn("enabled: !deckConfig.inComputerMode", result)
        self.assertIn(led.GUARD.strip(), result)
        self.assertIn("deckConfig.songLoaded && deckConfig.playing", result)
        self.assertIn("deckConfig.tempoSyncedFlashState ? 127 : 0", result)

    def test_fx_keeps_native_inactive_and_routing(self):
        raw = b'''Item {
    id: module
    function send() { device.sendSimpleColor(6, 6, ledValue) }
    readonly property int ledValue: {
        if (fxOn && (!module.flashOnActive || globalConfig.flashStateFast)) { 127 } else { 1 }
    }
}
'''
        with patch.dict(led.HASHES, {"DJFxActivate.qml": hashlib.sha256(raw).hexdigest()}):
            result = led.transform("DJFxActivate.qml", raw).decode()
        self.assertIn("module.scPrime4SteadyLEDs || !module.flashOnActive", result)
        self.assertIn("device.sendSimpleColor(6, 6, ledValue)", result)
        self.assertIn("else { 1 }", result)

if __name__ == "__main__":
    unittest.main()
