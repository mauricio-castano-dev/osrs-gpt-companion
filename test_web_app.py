import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
import memory_db
import web_app
from state_monitor import StateMonitor
from test_queries import fixture


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(memory_db, 'DB_PATH', Path(self.temp.name) / 'test.sqlite3')
        self.db_patch.start()
        self.monitor = StateMonitor('ExamplePlayer.json')
        self.monitor._state = fixture()
        self.monitor._pending = False
        self.monitor._error = None
        self.answer = Mock(side_effect=self.reply)
        self.server = web_app.create_server(self.monitor, 'test-model', 0, answer_fn=self.answer)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.http = requests.Session()
        self.http.trust_env = False
        self.base = self.server.origin

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.http.close()
        self.db_patch.stop()
        self.temp.cleanup()

    def reply(self, message, model, history, router, on_tool_call):
        on_tool_call('query_player_stats', True)
        return 'Respuesta de prueba.'

    def post(self, path, data, **headers):
        return self.http.post(self.base + path, json=data,
                              headers={'X-CSRF-Token': self.server.app.csrf, **headers}, timeout=5)

    def test_status_and_assets_are_local_and_do_not_call_model(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')
        result = self.http.get(self.base + '/api/status', timeout=5)
        self.assertEqual(result.status_code, 200)
        data = result.json()
        self.assertEqual(data['model'], 'test-model')
        self.assertTrue(data['stats']['ok'])
        self.assertIn('freshness', data)
        self.assertNotIn('items', data['items']['bank'])
        self.answer.assert_not_called()
        html = self.http.get(self.base, timeout=5)
        self.assertIn(self.server.app.csrf, html.text)
        self.assertIn('frame-ancestors', html.headers['Content-Security-Policy'])
        self.assertEqual(html.headers['Cache-Control'], 'no-store')
        for path in ('/app.js', '/app.css'):
            self.assertEqual(self.http.get(self.base + path, timeout=5).status_code, 200)
        self.assertEqual(self.http.get(self.base + '/private', timeout=5).status_code, 404)

    def test_memories_list_delete_and_validation(self):
        key = memory_db.save_memory('Goal', '<script>fictional text</script>')['id']
        data = self.http.get(self.base + '/api/memories', timeout=5).json()
        self.assertEqual(data['memories'][0]['id'], key)
        self.assertEqual(self.post('/api/memories/delete', {'id': key}).json(), {'deleted': True, 'id': key})
        self.assertFalse(self.post('/api/memories/delete', {'id': key}).json()['deleted'])
        for value in (True, '1', -1, None):
            self.assertEqual(self.post('/api/memories/delete', {'id': value}).status_code, 400)
        key = memory_db.save_memory('Another', 'Fictional')['id']
        result = self.http.delete(self.base + '/api/memories/delete', json={'id': key},
                                  headers={'X-CSRF-Token': self.server.app.csrf}, timeout=5)
        self.assertTrue(result.json()['deleted'])
        self.answer.assert_not_called()

    def test_chat_collects_tools_keeps_six_exchanges_and_clears_locally(self):
        for i in range(8):
            response = self.post('/api/chat', {'message': f'Question {i}'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['tools_used'], [{'name': 'query_player_stats', 'ok': True}])
            self.assertIn('lastUpdated', response.json())
        self.assertEqual(len(self.server.app.history), 12)
        self.assertEqual(self.server.app.history[0]['content'], 'Question 2')
        self.assertEqual(self.post('/api/chat', {'message': '/limpiar'}).status_code, 200)
        self.assertEqual(self.server.app.history, [])
        self.assertEqual(self.answer.call_count, 8)

    def test_csrf_origin_host_and_loopback_guards(self):
        for path, data in [('/api/chat', {'message': 'hello'}), ('/api/memories/delete', {'id': 1})]:
            self.assertEqual(self.http.post(self.base + path, json=data, timeout=5).status_code, 403)
            self.assertEqual(self.post(path, data, **{'X-CSRF-Token': 'wrong'}).status_code, 403)
            self.assertEqual(self.post(path, data, Origin='https://external.example').status_code, 403)
            self.assertEqual(self.post(path, data, **{'Sec-Fetch-Site': 'cross-site'}).status_code, 403)
            self.assertEqual(self.post(path, data, Host='rebind.example').status_code, 403)
        self.assertEqual(self.http.get(self.base + '/api/status', headers={'Origin': 'https://external.example'}, timeout=5).status_code, 403)
        self.assertFalse(web_app.allowed_request('203.0.113.1', self.base.split('//')[1], None, None, self.base))
        self.assertFalse(web_app.allowed_request('invalid', self.base.split('//')[1], None, None, self.base))
        self.assertTrue(web_app.allowed_request('127.0.0.1', self.base.split('//')[1], self.base, 'same-origin', self.base))
        self.answer.assert_not_called()

    def test_bad_requests_and_concurrent_chat_do_not_trigger_model(self):
        for message in ('', ' ' * 3, 'x' * 8001, True, None, '/unknown'):
            self.assertEqual(self.post('/api/chat', {'message': message}).status_code, 400)
        self.server.app.lock.acquire()
        try:
            self.assertEqual(self.post('/api/chat', {'message': 'hello'}).status_code, 409)
            self.assertEqual(self.http.get(self.base + '/api/status', timeout=5).status_code, 200)
            self.assertEqual(self.post('/api/memories/delete', {'id': 1}).status_code, 409)
        finally:
            self.server.app.lock.release()
        bad = self.http.post(self.base + '/api/chat', data='{', headers={
            'Content-Type': 'application/json', 'X-CSRF-Token': self.server.app.csrf}, timeout=5)
        self.assertEqual(bad.status_code, 400)
        self.answer.assert_not_called()

    def test_model_error_does_not_commit_partial_history(self):
        self.answer.side_effect = web_app.CompanionError('sensitive internals')
        result = self.post('/api/chat', {'message': 'test'})
        self.assertEqual(result.status_code, 502)
        self.assertNotIn('sensitive', result.text)
        self.assertEqual(self.server.app.history, [])

    def test_occupied_port_uses_a_free_loopback_port(self):
        with web_app.create_server(self.monitor, 'test', self.server.server_port) as other:
            self.assertNotEqual(other.server_port, self.server.server_port)
            self.assertEqual(other.server_address[0], '127.0.0.1')


if __name__ == '__main__':
    unittest.main()
