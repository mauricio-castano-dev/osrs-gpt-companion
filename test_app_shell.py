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
import web_app


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
    def test_browser_flag_forces_external_browser_without_changing_default_serve_contract(self):
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as folder:
            monitor=MagicMock()
            monitor.__enter__.return_value=monitor
            with patch.object(sys,'argv',['main.py','--browser']), patch.object(main,'AUTH_DIR',Path(folder)), \
                 patch.object(main,'host_id'), patch.object(main,'load_settings',return_value={}), \
                 patch.object(main,'list_models',return_value=[{'slug':'test-model'}]), \
                 patch.object(main,'StateMonitor',return_value=monitor),patch('web_app.serve') as serve:
                main.run(default_ui=False)
            serve.assert_called_once_with(monitor,'test-model',port=8765,prefer_native=False)
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


class NativeWindowTests(unittest.TestCase):
    def server_fixture(self):
        from unittest.mock import MagicMock
        server=MagicMock()
        server.__enter__.return_value=server
        server.origin='http://127.0.0.1:12345'
        server.app.window=web_app.WindowController()
        return server

    def test_native_window_created_attached_and_server_shutdown_on_close(self):
        server=self.server_fixture()
        view=Mock()
        window=view.create_window.return_value
        def start(**kwargs):
            self.assertTrue(server.app.window.state()['native'])
            self.assertIs(server.app.window._window,window)
        view.start.side_effect=start
        with patch('web_app.create_server',return_value=server),patch.dict(sys.modules,{'webview':view}), \
             patch('web_app.webbrowser.open') as browser,contextlib.redirect_stdout(io.StringIO()):
            web_app.serve(Mock(),'model')
        view.create_window.assert_called_once_with('RuneScribe · OSRS Companion',server.origin,
            width=440,height=860,min_size=(360,580),resizable=True,on_top=False,background_color='#090d16')
        view.start.assert_called_once()
        server.shutdown.assert_called_once()
        browser.assert_not_called()

    def test_native_failure_stops_background_server_then_falls_back_to_browser(self):
        server=self.server_fixture()
        view=Mock()
        view.start.side_effect=RuntimeError('Missing WebView2')
        with patch('web_app.create_server',return_value=server),patch.dict(sys.modules,{'webview':view}), \
             patch('web_app.webbrowser.open') as browser,contextlib.redirect_stdout(io.StringIO()):
            web_app.serve(Mock(),'model')
        server.shutdown.assert_called_once()
        self.assertEqual(server.serve_forever.call_count,2)
        browser.assert_called_once_with(server.origin)
        self.assertFalse(server.app.window.state()['native'])

    def test_browser_fallback_and_explicit_browser_skip_native_start(self):
        for prefer_native in (False,True):
            server=self.server_fixture()
            with patch('web_app.create_server',return_value=server),patch.dict(sys.modules,{'webview':None}), \
                 patch('web_app.webbrowser.open') as browser,contextlib.redirect_stdout(io.StringIO()):
                web_app.serve(Mock(),'model',prefer_native=prefer_native)
            browser.assert_called_once_with(server.origin)
            server.shutdown.assert_not_called()
            server.serve_forever.assert_called_once_with(poll_interval=0.2)

    def test_closing_mock_native_window_releases_real_http_port(self):
        from urllib.parse import urlsplit
        view=Mock()
        with patch.dict(sys.modules,{'webview':view}),patch('web_app.webbrowser.open'),contextlib.redirect_stdout(io.StringIO()):
            web_app.serve(Mock(),'model',port=0)
        port=urlsplit(view.create_window.call_args.args[1]).port
        with web_app.create_server(Mock(),'model',port) as server:
            self.assertEqual(server.server_port,port)


if __name__ == '__main__':
    unittest.main()
