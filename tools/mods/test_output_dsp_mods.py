import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'ui-mod'))
import output_dsp_ui
spec = importlib.util.spec_from_file_location('output_dsp_builder', HERE / 'build_output_dsp_mods.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

class OutputDSPMods(unittest.TestCase):
    def test_archives_are_reproducible_and_qml_only(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            builder.build(Path(first)); builder.build(Path(second))
            for mid, *_ in builder.MODS:
                name = mid + '-0.1.0.tar.gz'
                raw = (Path(first) / name).read_bytes()
                self.assertEqual(raw, (Path(second) / name).read_bytes())
                with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
                    self.assertEqual(sorted(archive.getnames()), ['Panel.qml', 'README.md', 'mod.json'])
                    manifest = json.load(archive.extractfile('mod.json'))
                    self.assertNotIn('script', manifest)
                    self.assertFalse(manifest.get('official', False))
                    self.assertEqual(manifest['qmlFiles'], {'Panel.qml': f'EngineXMods/{mid}/Panel.qml'})
                    panel = archive.extractfile('Panel.qml').read().decode()
                    self.assertNotIn('@', panel)
                    self.assertIn('requestTimeout', panel)

    def fixture(self):
        return {'Skin/EmbeddedMain.qml': 'import QtQuick 2.12\nItem { id: root }',
                'Skin/MixerTabContent.qml': 'Item { property var entries: [EntryBase.ListEntry { text: "Fader Echo" }] }'}

    def test_missing_anchor_does_not_mutate_pack(self):
        base = self.fixture(); del base['Skin/MixerTabContent.qml']; old = copy.deepcopy(base)
        with patch.object(output_dsp_ui, 'feature', return_value=True):
            with self.assertRaises(RuntimeError): output_dsp_ui.add_output_dsp(base, Path('/unused'), 'Skin/')
        self.assertEqual(base, old)

    def test_controls_only_load_on_explicit_open(self):
        base = self.fixture()
        with patch.object(output_dsp_ui, 'feature', return_value=True):
            output_dsp_ui.add_output_dsp(base, Path('/unused'), 'Skin/')
        main = base['Skin/EmbeddedMain.qml']
        self.assertNotIn('import QtQuick.Controls', main)
        self.assertIn('active: false; asynchronous: true', main)
        self.assertIn('onStatusChanged: if(status===Loader.Error)active=false', main)
        self.assertIn('root.scBoard !== "JC11"', main)
        self.assertNotIn('TouchFxButton', main)

    def test_core_branch_has_no_ui_changes(self):
        base = self.fixture(); old = copy.deepcopy(base)
        with patch.object(output_dsp_ui, 'feature', return_value=False):
            output_dsp_ui.add_output_dsp(base, Path('/unused'), 'Skin/')
        self.assertEqual(base, old)

if __name__ == '__main__': unittest.main()
