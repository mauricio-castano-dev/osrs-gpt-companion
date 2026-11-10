"""Renderizado JS en DOM sintetico: Node es opcional, nunca necesario para usar la app."""
import shutil
import subprocess
import unittest
from pathlib import Path


class FrontendTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node no disponible para pruebas JS opcionales')
    def test_safe_dom_rendering_markdown_hud_and_progress(self):
        result = subprocess.run([shutil.which('node'), '--test', 'tests/ui.test.cjs'],
                                cwd=Path(__file__).resolve().parent, capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
