import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import inference
import main
import memory_db
from auth import CompanionError
from state_monitor import StateMonitor
from tools import TOOLS, ToolRouter


class AgentTests(unittest.TestCase):
    def test_safe_tool_names_callback_and_duplicate_notifications(self):
        final = [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'Done'}]}]
        for name, result, expected_name, ok in [
            ('osrs.query_player_stats', {'ok': True}, 'query_player_stats', True),
            ('check_ge_price', {'ok': False, 'error': 'Offline'}, 'check_ge_price', False),
            ('save_agent_memory', {'saved': False, 'duplicate': True}, 'save_agent_memory', True),
            ('malicious\nsecret', {'ok': False}, 'local', False),
            (None, {'ok': False}, 'local', False),
        ]:
            call = {'type': 'function_call', 'call_id': 'one', 'name': name, 'arguments': '{}'}
            router = Mock()
            router.execute.return_value = result
            callback = Mock()
            stream = io.StringIO()
            with patch.object(inference, 'response_round', side_effect=[[call], [call], final]), contextlib.redirect_stdout(stream):
                self.assertEqual(inference.answer('Question', 'model', [], router, callback), 'Done')
            callback.assert_called_once_with(expected_name, ok)
            router.execute.assert_called_once()
            label = f'[Consultando herramienta: {expected_name}]' if expected_name != 'local' else '[Consultando herramienta local]'
            self.assertEqual(stream.getvalue().strip(), label)
            self.assertNotIn('secret', stream.getvalue())

    def test_observer_failure_does_not_repeat_or_lose_tool_result(self):
        call = {'type': 'function_call', 'call_id': 'save', 'name': 'save_agent_memory', 'arguments': '{}'}
        final = [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'Saved'}]}]
        router = Mock()
        router.execute.return_value = {'saved': True}
        callback = Mock(side_effect=RuntimeError('secret observer internals'))
        stream = io.StringIO()
        with patch.object(inference, 'response_round', side_effect=[[call], final]), contextlib.redirect_stdout(stream):
            self.assertEqual(inference.answer('Save', 'model', [], router, callback), 'Saved')
        self.assertNotIn('secret', stream.getvalue())
        router.execute.assert_called_once()

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail('El monitor no recibio la actualizacion.')

    def test_watcher_partial_atomic_replace_delete_and_recreate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'player.json'
            path.write_text('{"skills":{"attack":10}}')
            with StateMonitor(path) as monitor:
                self.assertEqual(monitor.snapshot()['data']['skills']['attack'], 10)
                snapshot = monitor.snapshot()
                snapshot['data']['skills']['attack'] = 0
                self.assertEqual(monitor.snapshot()['data']['skills']['attack'], 10)
                path.write_text('{')
                self.wait_for(lambda: not monitor.snapshot()['ok'])
                replacement = Path(directory) / 'new.json'
                replacement.write_text('{"skills":{"attack":20}}')
                os.replace(replacement, path)
                self.wait_for(lambda: monitor.snapshot()['ok'] and monitor.snapshot()['data']['skills']['attack'] == 20)
                with patch.object(Path, 'open', side_effect=AssertionError('lectura por turno')):
                    self.assertTrue(monitor.snapshot()['ok'])
                path.unlink()
                self.wait_for(lambda: not monitor.snapshot()['ok'])
                path.write_text('{"quests":[]}')
                self.wait_for(lambda: monitor.snapshot()['ok'] and 'quests' in monitor.snapshot()['data'])

    def test_memory_persistence_literal_search_and_duplicates(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(memory_db, 'DB_PATH', Path(directory) / 'memory.db'):
            saved = memory_db.save_memory('Dragon Slayer II', 'Quiero terminar Dragon Slayer II sin guias.')
            self.assertTrue(saved['saved'])
            self.assertEqual(len(memory_db.search_memory('Dragon Slayer')), 1)
            self.assertEqual(len(memory_db.search_memory('Dragon OR Slayer')), 1)
            self.assertEqual(memory_db.search_memory('" OR 1=1 --'), [])
            self.assertTrue(memory_db.save_memory('Dragon Slayer II', 'Quiero terminar Dragon Slayer II sin guias.')['duplicate'])
            self.assertEqual(memory_db.search_memory('Dragon Slayer')[0]['id'], saved['id'])

    def test_router_rejects_unknown_tools_and_invalid_arguments(self):
        monitor = Mock()
        monitor.query_stats.return_value = {'ok': True, 'data': {'bank': {}}}
        router = ToolRouter(monitor)
        self.assertTrue(router.execute({'name': 'query_player_stats', 'arguments': json.dumps({'skills': [], 'include_slayer_and_timers': False}), 'namespace': 'osrs'})['ok'])
        for call in [
            {'name': 'shell', 'arguments': '{}'},
            {'name': 'query_player_stats', 'arguments': '{'},
            {'name': 'query_player_stats', 'arguments': '{"path":"secret"}'},
            {'name': 'save_agent_memory', 'arguments': '{"tema":2,"contenido":"x"}'},
            {'name': 'query_player_stats', 'arguments': '{}', 'namespace': 'other'},
        ]:
            self.assertFalse(router.execute(call)['ok'])

    def test_agent_round_trip_preserves_reasoning_and_tool_call_id(self):
        call = {'type': 'function_call', 'call_id': 'c1', 'name': 'query_player_stats', 'namespace': 'osrs', 'arguments': '{}'}
        reasoning = {'type': 'reasoning', 'id': 'r1', 'summary': [], 'encrypted_content': 'opaque'}
        final = [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'Plan listo'}]}]
        router = Mock()
        router.execute.return_value = {'ok': True, 'data': {'skills': {}}}
        seen = []
        def respond(model, items):
            seen.append(json.loads(json.dumps(items)))
            return [reasoning, call] if len(seen) == 1 else final
        with patch.object(inference, 'response_round', side_effect=respond), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(inference.answer('Plan', 'model', [], router), 'Plan listo')
        self.assertIn(reasoning, seen[1])
        self.assertIn(call, seen[1])
        self.assertEqual(seen[1][-1]['type'], 'function_call_output')
        self.assertEqual(seen[1][-1]['call_id'], 'c1')
        router.execute.assert_called_once_with(call)

    def test_repeated_call_is_not_executed_twice_and_loop_is_bounded(self):
        call = {'type': 'function_call', 'call_id': 'same', 'name': 'save_agent_memory', 'arguments': '{}'}
        router = Mock()
        router.execute.return_value = {'saved': True}
        with patch.object(inference, 'response_round', return_value=[call]) as respond, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(CompanionError):
                inference.answer('Guardar', 'model', [], router)
        self.assertEqual(respond.call_count, 8)
        router.execute.assert_called_once()

    def test_stream_requires_completed_and_sends_namespace(self):
        class Response:
            status_code = 200
            headers = {'Content-Type': 'text/event-stream'}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def iter_lines(self, **kwargs): return iter(self.lines)
        for kind in ('response.completed', 'response.failed', 'response.incomplete', 'response.output_item.done'):
            response = Response()
            response.lines = ['data: ' + json.dumps({'type': kind, 'response': {'output': []}}), '']
            with patch.object(inference.HTTP, 'post', return_value=response) as post, patch.object(inference, 'access_token', return_value='fake'):
                if kind == 'response.completed':
                    self.assertEqual(inference.response_round('model', []), [])
                else:
                    with self.assertRaises(CompanionError):
                        inference.response_round('model', [])
                payload = post.call_args.kwargs['json']
                self.assertIs(payload['store'], False)
                self.assertIs(payload['stream'], True)
                self.assertEqual(payload['tools'], TOOLS)
                self.assertEqual(payload['tools'][0]['type'], 'namespace')

    def test_missing_content_type_accepts_valid_sse_but_rejects_other_bodies(self):
        class Response:
            status_code = 200
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def iter_lines(self, **kwargs): return iter(self.lines)
        response = Response()
        output = [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'OK'}]}]
        response.lines = ['event: response.completed',
                          'data: ' + json.dumps({'type': 'response.completed', 'response': {'output': output}}), '']
        with patch.object(inference.HTTP, 'post', return_value=response), patch.object(inference, 'access_token', return_value='fake'):
            self.assertEqual(inference.response_round('model', []), output)
            for lines in (['<!doctype html>'], ['{"error":"failure"}'], ['data: {', ''],
                          ['data: []', ''], ['data: {"type":"response.completed"}']):
                response.lines = lines
                with self.assertRaises(CompanionError):
                    inference.response_round('model', [])
            response.headers = {'Content-Type': 'application/json'}
            with self.assertRaisesRegex(CompanionError, 'application/json'):
                inference.response_round('model', [])


class ConsoleTests(unittest.TestCase):
    def monitor(self):
        monitor = Mock()
        monitor.path = Path('fictional.json')
        monitor.query_stats.return_value = {'ok': True, 'lastUpdated': '2026-11-09T00:00:00Z',
            'player': {'username': 'ExamplePlayer', 'combatLevel': 50, 'world': 330},
            'timers': {'farming': {'active_count': 20}}}
        monitor.query_items.return_value = {'ok': True, 'currency': {
            'bank': {'gp_equivalent': 10000}, 'inventory': {'gp_equivalent': 200}}}
        return monitor

    def test_local_commands_never_call_model_and_do_not_enter_history(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(memory_db, 'DB_PATH', Path(folder) / 'memory.db'):
            memory_id = memory_db.save_memory('Quest Cape', 'My goal')['id']
            stream = io.StringIO()
            monitor = self.monitor()
            inputs = ['/estado', '/memorias', f'/olvidar {memory_id}', f'/olvidar {memory_id}', '/memorias',
                      '/olvidar', '/olvidar true', '/olvidar 0', '/olvidar -1', '/olvidar 2 extra', '/unknown', '/salir']
            with patch('builtins.input', side_effect=inputs), patch.object(main, 'answer') as answer, contextlib.redirect_stdout(stream):
                main.chat('model', monitor)
            answer.assert_not_called()
            text = stream.getvalue()
            self.assertIn('ok=True', text)
            self.assertIn('ExamplePlayer | Combate: 50 | Mundo: 330', text)
            self.assertIn('banco=10000 | inventario=200', text)
            self.assertIn('farming: 20', text)
            self.assertIn(f'[#{memory_id}]', text)
            self.assertIn(f'Memoria #{memory_id} eliminada.', text)
            self.assertIn(f'No existe la memoria #{memory_id}.', text)
            self.assertIn('No hay memorias guardadas.', text)
            self.assertGreaterEqual(text.count('Uso:'), 3)
            self.assertEqual(memory_db.list_memories(), [])
            monitor.query_stats.assert_called_once_with([], True)
            monitor.query_items.assert_called_once_with('', 'all')

    def test_estado_is_five_lines_and_unavailable_state_hides_old_values(self):
        monitor = self.monitor()
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            main.print_local_state(monitor)
        self.assertEqual(len(stream.getvalue().splitlines()), 5)
        monitor.query_stats.return_value = {'ok': False, 'error': 'Pending', 'player': {'username': 'STALE'}}
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            main.print_local_state(monitor)
        self.assertNotIn('STALE', stream.getvalue())
        self.assertIn('ok=False', stream.getvalue())
        self.assertEqual(len(stream.getvalue().splitlines()), 4)

    def test_database_error_during_local_command_does_not_end_chat(self):
        import sqlite3
        with patch('builtins.input', side_effect=['/memorias', '/salir']), \
             patch.object(main, 'list_memories', side_effect=sqlite3.OperationalError()), \
             patch.object(main, 'answer') as answer, contextlib.redirect_stdout(io.StringIO()) as stream:
            main.chat('model', self.monitor())
        answer.assert_not_called()
        self.assertIn('No se pudo acceder', stream.getvalue())


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.auth_dir = self.folder / '.auth'
        self.auth_dir.mkdir()
        self.patch = patch.object(main, 'AUTH_DIR', self.auth_dir)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.state = self.folder / 'ExamplePlayer.json'
        self.state.write_text('{"player":{"username":"ExamplePlayer"}}', encoding='utf-8')

    def invoke(self, arguments, models=None):
        monitor = Mock()
        monitor.path = self.state
        monitor.snapshot.return_value = {'ok': True}
        monitor.__enter__ = Mock(return_value=monitor)
        monitor.__exit__ = Mock(return_value=False)
        with patch.object(sys, 'argv', ['main.py', *arguments]), \
             patch.object(main, 'host_id'), patch.object(main, 'StateMonitor', return_value=monitor) as start, \
             patch.object(main, 'list_models', return_value=models or [{'slug': 'first'}, {'slug': 'chosen'}]) as list_models, \
             patch.object(main, 'chat') as chat, contextlib.redirect_stdout(io.StringIO()):
            main.run()
        return start, list_models, chat

    def test_atomic_settings_merge_and_corrupt_missing_file_recovery(self):
        self.assertEqual(main.load_settings(), {})
        main.save_settings(state_file=self.state)
        main.save_settings(model='chosen')
        self.assertEqual(main.load_settings(), {'state_file': str(self.state.resolve()), 'model': 'chosen'})
        self.assertFalse((self.auth_dir / 'settings.json.tmp').exists())
        # Una sustitucion atomica fallida conserva la configuracion anterior.
        with patch('auth.os.replace', side_effect=OSError('disk busy')):
            with self.assertRaises(OSError):
                main.save_settings(model='new')
        self.assertEqual(main.load_settings()['model'], 'chosen')
        self.state.unlink()
        self.assertEqual(main.load_settings(), {'model': 'chosen'})
        for raw in ('{', '[]', '{"model": false}', '{"state_file": 7}', '{"model":""}'):
            (self.auth_dir / 'settings.json').write_text(raw, encoding='utf-8')
            self.assertEqual(main.load_settings(), {})

    def test_explicit_cli_choices_are_saved_and_reused_on_next_launch(self):
        self.invoke(['--state-file', str(self.state), '--model', 'chosen'])
        self.assertEqual(main.load_settings(), {'state_file': str(self.state.resolve()), 'model': 'chosen'})
        start, _, chat = self.invoke([])
        start.assert_called_once_with(str(self.state.resolve()))
        self.assertEqual(chat.call_args.args[0], 'chosen')

    def test_cli_overrides_saved_model_and_unavailable_saved_model_falls_back(self):
        main.save_settings(state_file=self.state, model='missing')
        _, _, chat = self.invoke([])
        self.assertEqual(chat.call_args.args[0], 'first')
        # Los defaults temporales no reemplazan la eleccion guardada.
        self.assertEqual(main.load_settings()['model'], 'missing')
        self.invoke(['--model', 'chosen'])
        self.assertEqual(main.load_settings()['model'], 'chosen')
        self.assertIn('state_file', main.load_settings())

    def test_check_state_persists_valid_path_without_contacting_openai(self):
        _, list_models, chat = self.invoke(['--check-state', '--state-file', str(self.state)])
        self.assertEqual(main.load_settings()['state_file'], str(self.state.resolve()))
        list_models.assert_not_called()
        chat.assert_not_called()

    def test_invalid_explicit_model_does_not_overwrite_saved_choices(self):
        main.save_settings(state_file=self.state, model='chosen')
        with self.assertRaises(CompanionError):
            self.invoke(['--model', 'unavailable'])
        self.assertEqual(main.load_settings()['model'], 'chosen')

    def test_nonexistent_saved_path_uses_legacy_fallback_without_saving_it(self):
        (self.auth_dir / 'settings.json').write_text(json.dumps({'state_file': str(self.folder / 'missing.json')}))
        with patch.object(main, 'default_state_path', return_value=self.state):
            start, _, _ = self.invoke([])
        start.assert_called_once_with(str(self.state))
        self.assertNotIn('state_file', main.load_settings())

    def test_real_monitor_preserves_last_valid_path_when_new_json_is_broken(self):
        main.save_settings(state_file=self.state, model='chosen')
        other = self.folder / 'OtherPlayer.json'
        other.write_text('{', encoding='utf-8')
        with patch.object(sys, 'argv', ['main.py', '--state-file', str(other)]), \
             patch.object(main, 'host_id'), patch.object(main, 'chat'), \
             patch.object(main, 'list_models', return_value=[{'slug': 'chosen'}]), \
             contextlib.redirect_stdout(io.StringIO()):
            main.run()
        self.assertEqual(main.load_settings()['state_file'], str(self.state.resolve()))
        other.write_text('{"player":{}}', encoding='utf-8')
        with patch.object(sys, 'argv', ['main.py', '--state-file', str(other)]), \
             patch.object(main, 'host_id'), patch.object(main, 'chat'), \
             patch.object(main, 'list_models', return_value=[{'slug': 'chosen'}]), \
             contextlib.redirect_stdout(io.StringIO()):
            main.run()
        self.assertEqual(main.load_settings()['state_file'], str(other.resolve()))


if __name__ == '__main__':
    unittest.main()
