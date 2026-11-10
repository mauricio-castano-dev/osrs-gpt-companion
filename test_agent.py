import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import inference
import memory_db
from auth import CompanionError
from state_monitor import StateMonitor
from tools import TOOLS, ToolRouter


class AgentTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
