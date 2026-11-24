import contextlib
import io
from pathlib import Path
import tempfile
import unittest
import inspect_button_leds

class ButtonLEDEvidence(unittest.TestCase):
    def test_reports_hash_and_relevant_assignment_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'JC11_Controller_Assignments.qml'
            data=b'Item { property bool playState: false; property bool blink: true }\n'
            path.write_bytes(data)
            output=io.StringIO()
            with contextlib.redirect_stdout(output):inspect_button_leds.inventory(root)
            self.assertIn('sha256=',output.getvalue());self.assertIn('playState',output.getvalue())
            self.assertEqual(path.read_bytes(),data)

    def test_skips_symlinks_and_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external:
            root=Path(directory);outside=Path(external)/'JC11_Assignments.qml'
            outside.write_text('Item { property bool fxEnable: true; property bool blink: true }')
            (root/'JC11_Link.qml').symlink_to(outside)
            (root/'Unrelated.qml').write_text('Item { property bool fxEnable: true; property bool blink: true }')
            output=io.StringIO()
            with contextlib.redirect_stdout(output):inspect_button_leds.inventory(root)
            self.assertEqual(output.getvalue(),'')

if __name__=='__main__':unittest.main()
