import contextlib
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import launcher
import main
import state_monitor


class FrozenDate(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 9, 12, tzinfo=timezone.utc)


class RelativeTimeTests(unittest.TestCase):
    def test_recent_old_offset_future_and_invalid_timestamps(self):
        with patch.object(state_monitor, 'datetime', FrozenDate):
            now = FrozenDate.now()
            for delta, expected in [(8, 'hace 8 s'), (240, 'hace 4 min'), (7200, 'hace 2 h'), (172800, 'hace 2 d')]:
                stamp = (now - timedelta(seconds=delta)).isoformat().replace('+00:00','Z')
                self.assertEqual(state_monitor.format_relative_time(stamp), expected)
            self.assertEqual(state_monitor.format_relative_time('2026-11-09T07:00:00-05:00'), 'hace 0 s')
            self.assertEqual(state_monitor.format_relative_time('2026-11-10T12:00:00Z'), 'hace 0 s')
            for value in (None, '', 'broken', '2026-11-09T12:00:00', 3):
                self.assertEqual(state_monitor.format_relative_time(value), 'sin fecha')

    def test_default_prefers_newest_file_and_has_safe_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / 'project'
            project.mkdir()
            home = root / 'home'
            exported = home / '.runelite' / 'osrs-companion' / 'kpn_hooligan.json'
            exported.parent.mkdir(parents=True)
            local = project / 'kpn_hooligan.json'
            with patch.object(state_monitor.Path, 'home', return_value=home), patch.object(state_monitor, '__file__', str(project / 'state_monitor.py')):
                self.assertEqual(state_monitor.default_state_path(), local)
                exported.write_text('{}')
                self.assertEqual(state_monitor.default_state_path(), exported)
                local.write_text('{}')
                os.utime(exported, ns=(100,100))
                os.utime(local, ns=(200,200))
                self.assertEqual(state_monitor.default_state_path(), local)
                os.utime(exported, ns=(300,300))
                self.assertEqual(state_monitor.default_state_path(), exported)

    def test_console_footer_is_separate_and_color_is_optional(self):
        monitor = Mock()
        monitor.freshness_summary.return_value = {'lastUpdated': None}
        for supports in (False, True):
            stream = io.StringIO()
            with patch.object(main,'supports_ansi',return_value=supports), contextlib.redirect_stdout(stream):
                main.print_freshness(monitor)
            self.assertIn('Instantánea: sin fecha', stream.getvalue())
            self.assertEqual('\033[90m' in stream.getvalue(), supports)


class LauncherTests(unittest.TestCase):
    def test_ui_default_explicit_ui_and_cli_modes_route_correctly(self):
        from unittest.mock import MagicMock
        for args, default_ui, expect_ui in [([], True, True), (['--cli'], True, False), (['--ui','--port','9000'], False, True)]:
            with tempfile.TemporaryDirectory() as folder:
                monitor = MagicMock()
                monitor.__enter__.return_value = monitor
                with patch.object(sys,'argv',['main.py',*args]), patch.object(main,'AUTH_DIR',Path(folder)), \
                     patch.object(main,'host_id'), patch.object(main,'load_settings',return_value={}), \
                     patch.object(main,'list_models',return_value=[{'slug':'test-model'}]), \
                     patch.object(main,'StateMonitor',return_value=monitor), patch.object(main,'chat') as chat, \
                     patch('web_app.serve') as serve:
                    main.run(default_ui=default_ui)
                self.assertEqual(serve.called,expect_ui)
                self.assertEqual(chat.called,not expect_ui)
                if '--port' in args:
                    self.assertEqual(serve.call_args.kwargs['port'],9000)

    def test_path_append_is_idempotent_and_preserves_entries(self):
        current = r'C:\One;%USERPROFILE%\Existing'
        updated = launcher.append_user_path(current, r'C:\OSRS\bin')
        self.assertEqual(updated, current + r';C:\OSRS\bin')
        self.assertEqual(launcher.append_user_path(updated, 'c:\\osrs\\bin\\'), updated)

    def test_install_writes_absolute_quoted_launchers_without_changing_real_path(self):
        with tempfile.TemporaryDirectory(prefix='OSRS launcher ') as temp:
            root = Path(temp)
            python = root / '.venv' / 'Scripts' / 'python.exe'
            python.parent.mkdir(parents=True)
            python.write_bytes(b'fixture')
            (root/'main.py').write_text('# fixture')
            bin_path = root / 'bin'
            with patch.object(launcher.sys,'platform','win32'), patch.object(launcher,'register_user_path') as register:
                self.assertEqual(launcher.install_path(root,bin_path), bin_path)
            register.assert_called_once_with(bin_path)
            for directory in (root,bin_path):
                text = (directory/'osrs-companion.cmd').read_text()
                self.assertIn('"'+str(python)+'"',text)
                self.assertIn('"'+str(root/'main.py')+'"',text)
                self.assertIn('%*',text)
                self.assertIn('--ui', (directory/'osrs-companion-ui.cmd').read_text())

    def test_entry_points_default_to_ui_and_install_does_not_authenticate(self):
        with patch.object(main,'run') as run:
            self.assertEqual(main.main(),0)
            run.assert_called_once_with(default_ui=True,force_ui=False)
        with patch.object(main,'run') as run:
            self.assertEqual(main.run_ui(),0)
            run.assert_called_once_with(default_ui=True,force_ui=True)
        with patch.object(sys,'argv',['main.py','--install-path']), patch.object(launcher,'install_path',return_value=Path('bin')) as install, patch.object(main,'list_models') as models, patch.object(main,'host_id') as host, contextlib.redirect_stdout(io.StringIO()):
            main.run()
        install.assert_called_once()
        models.assert_not_called()
        host.assert_not_called()


if __name__ == '__main__':
    unittest.main()
