import json
import re
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
        self.models = Mock(return_value=[{'slug': 'test-model', 'display_name': 'Test'}, {'slug': 'other'}])
        self.save_settings = Mock()
        self.ge = Mock(return_value={'ok': True, 'matches': [{'name': 'Example item', 'high': 10, 'low': 9}]})
        self.wiki = Mock(return_value={'ok': True, 'extract': 'Example extract', 'results': []})
        self.server = web_app.create_server(self.monitor, 'test-model', 0, answer_fn=self.answer,
                                            models_fn=self.models, save_settings_fn=self.save_settings,
                                            ge_fn=self.ge, wiki_fn=self.wiki)
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
        self.assertFalse(data['busy'])
        self.assertEqual(data['active_tools'], [])
        self.assertIn('freshness', data)
        self.assertNotIn('items', data['items']['bank'])
        self.answer.assert_not_called()
        html = self.http.get(self.base, timeout=5)
        self.assertIn(self.server.app.csrf, html.text)
        for name in ('tab-state', 'tab-gear', 'tab-memory', 'gear-content'):
            self.assertIn(f'id="{name}"', html.text)
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
        status = self.http.get(self.base + '/api/status', timeout=5).json()
        self.assertFalse(status['busy'])
        self.assertEqual(status['active_tools'], [])

    def test_live_status_reports_tools_during_chat_then_clears_on_completion(self):
        ready = threading.Event()
        release = threading.Event()
        results = []
        def delayed_answer(message, model, history, router, on_tool_call):
            on_tool_call('query_player_stats', True)
            on_tool_call('check_ge_price', False)
            ready.set()
            if not release.wait(5):
                raise RuntimeError('Test did not release answer')
            return 'Done'
        self.answer.side_effect = delayed_answer
        def send_chat():
            with requests.Session() as http:
                http.trust_env = False
                results.append(http.post(self.base + '/api/chat', json={'message': 'test'},
                               headers={'X-CSRF-Token': self.server.app.csrf}, timeout=8))
        worker = threading.Thread(target=send_chat)
        worker.start()
        try:
            self.assertTrue(ready.wait(5))
            status = self.http.get(self.base + '/api/status', timeout=5).json()
            expected = [{'name': 'query_player_stats', 'ok': True}, {'name': 'check_ge_price', 'ok': False}]
            self.assertTrue(status['busy'])
            self.assertEqual(status['active_tools'], expected)
            status['active_tools'][0]['name'] = 'mutated copy'
            self.assertEqual(self.server.app.status()['active_tools'], expected)
        finally:
            release.set()
            worker.join(8)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0].status_code, 200)
        self.assertEqual(results[0].json()['tools_used'], expected)
        final = self.http.get(self.base + '/api/status', timeout=5).json()
        self.assertFalse(final['busy'])
        self.assertEqual(final['active_tools'], [])

    def test_failed_chat_also_clears_live_tool_progress(self):
        def fail(message, model, history, router, on_tool_call):
            on_tool_call('search_osrs_wiki', False)
            raise web_app.CompanionError('Offline')
        self.answer.side_effect = fail
        self.assertEqual(self.post('/api/chat', {'message': 'test'}).status_code, 502)
        self.assertEqual(self.server.app.active_tools, [])
        self.assertFalse(self.server.app.status()['busy'])

    def test_clear_history_resets_tool_progress_without_inference(self):
        self.server.app.active_tools = [{'name': 'old', 'ok': True}]
        self.assertEqual(self.post('/api/chat', {'message': '/limpiar'}).status_code, 200)
        self.assertEqual(self.server.app.active_tools, [])
        self.answer.assert_not_called()

    def test_occupied_port_uses_a_free_loopback_port(self):
        with web_app.create_server(self.monitor, 'test', self.server.server_port) as other:
            self.assertNotEqual(other.server_port, self.server.server_port)
            self.assertEqual(other.server_address[0], '127.0.0.1')

    def test_bank_search_is_filtered_in_ram_without_inference(self):
        with patch.object(Path, 'open', side_effect=AssertionError('No disk reads')):
            result = self.http.get(self.base + '/api/bank', params={'q': '  TEST ORE  '}, timeout=5)
            self.assertEqual(result.status_code, 200)
            data = result.json()
            self.assertEqual(data['bank']['total_matches'], 800)
            self.assertEqual(data['bank']['bank_total_items'], 802)
            self.assertEqual(len(data['bank']['items']), 30)
            self.assertEqual(data['inventory'], [])
            self.assertIn('currency', data)
            result = self.http.get(self.base + '/api/bank?q=fire', timeout=5).json()
            self.assertEqual(result['inventory'][0]['name'], 'Fire rune')
            self.assertEqual(result['bank']['total_matches'], 0)
        for query in ('x' * 101, 'bad\x00query'):
            self.assertEqual(self.http.get(self.base + '/api/bank', params={'q': query}, timeout=5).status_code, 400)
        empty = self.http.get(self.base + '/api/bank', timeout=5).json()
        self.assertNotIn('items', empty['bank'])
        self.answer.assert_not_called()
        self.models.assert_not_called()

    def test_model_catalog_is_cached_and_change_is_persisted_for_next_chat(self):
        for _ in range(2):
            data = self.http.get(self.base + '/api/models', timeout=5).json()
            self.assertEqual(data, {'current': 'test-model', 'models': [
                {'slug': 'test-model', 'display_name': 'Test'}, {'slug': 'other', 'display_name': 'other'}]})
        self.models.assert_called_once_with()
        self.assertEqual(self.post('/api/model', {'model': 'other'}).json(), {'ok': True, 'model': 'other'})
        self.save_settings.assert_called_once_with(model='other')
        self.assertEqual(self.http.get(self.base + '/api/models', timeout=5).json()['current'], 'other')
        self.post('/api/chat', {'message': 'hello'})
        self.assertEqual(self.answer.call_args.args[1], 'other')

    def test_model_mutation_validation_csrf_origin_and_busy(self):
        for data in ({'model': 'missing'}, {'model': None}, {'model': []}, {}, {'model': 'other', 'extra': 1}):
            self.assertEqual(self.post('/api/model', data).status_code, 400)
        self.assertEqual(self.http.post(self.base + '/api/model', json={'model': 'other'}, timeout=5).status_code, 403)
        self.assertEqual(self.post('/api/model', {'model': 'other'}, Origin='https://external.example').status_code, 403)
        self.server.app.lock.acquire()
        try:
            self.assertEqual(self.post('/api/model', {'model': 'other'}).status_code, 409)
        finally:
            self.server.app.lock.release()
        self.assertEqual(self.server.app.model, 'test-model')
        self.save_settings.assert_not_called()
        self.answer.assert_not_called()

    def test_model_catalog_offline_retries_and_persistence_failure_is_atomic(self):
        self.models.side_effect = web_app.CompanionError('secret')
        response = self.http.get(self.base + '/api/models', timeout=5)
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('secret', response.text)
        self.models.side_effect = None
        self.save_settings.side_effect = OSError('private path')
        response = self.post('/api/model', {'model': 'other'})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('private path', response.text)
        self.assertEqual(self.server.app.model, 'test-model')
        self.assertFalse(self.server.app.lock.locked())

    def test_new_controls_and_security_policy_are_served(self):
        response = self.http.get(self.base, timeout=5)
        for name in ('bank-search', 'bank-results', 'model-select'):
            self.assertIn(f'id="{name}"', response.text)
        self.assertIn("script-src 'self'", response.headers['Content-Security-Policy'])
        self.assertNotIn('unsafe-inline', response.headers['Content-Security-Policy'])

    def test_progress_filters_quests_diaries_and_combat_in_ram_without_model(self):
        self.monitor._state['combatAchievements'] = {'tasks': [
            {'name': f'Example challenge {i}', 'tier': 'EASY', 'monster': 'Example boss', 'completed': i % 2 == 0}
            for i in range(60)]}
        with patch.object(Path, 'open', side_effect=AssertionError('No disk per query')):
            def search(**params):
                result = self.http.get(self.base + '/api/progress', params=params, timeout=5)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.headers['Cache-Control'], 'no-store')
                return result.json()
            quests = search(q='  quest 1  ', category='quests', status='completed')
            self.assertTrue(quests['quests'])
            self.assertTrue(all('quest 1' in q['displayName'].lower() and q['state'] == 'FINISHED' for q in quests['quests']))
            self.assertNotIn('achievementDiaries', quests)
            diaries = search(q='ardougne', category='diaries', status='incomplete')['achievementDiaries']
            self.assertEqual(set(diaries), {'ARDOUGNE'})
            self.assertEqual(diaries['ARDOUGNE']['total_matches'], 40)
            self.assertEqual(len(diaries['ARDOUGNE']['tasks']), 30)
            self.assertTrue(all(task['completed'] is False for task in diaries['ARDOUGNE']['tasks']))
            combat = search(q='example boss', category='combat_achievements', status='completed')['combatAchievements']
            self.assertEqual(combat['total_matches'], 30)
            self.assertEqual(len(combat['tasks']), 25)
            self.assertTrue(combat['truncated'])
            self.assertTrue(all(task['completed'] for task in combat['tasks']))
        self.assertEqual(self.server.app.history, [])
        self.answer.assert_not_called()
        self.models.assert_not_called()

    def test_progress_invalid_filters_are_400_before_querying_monitor(self):
        with patch.object(self.monitor, 'query_quests_diaries', wraps=self.monitor.query_quests_diaries) as query:
            for params in ({'category': 'invalid'}, {'status': 'invalid'}, {'q': 'x' * 101},
                           {'q': 'bad\x00term'}, {'category': ''}, {'status': ''}):
                response = self.http.get(self.base + '/api/progress', params=params, timeout=5)
                self.assertEqual(response.status_code, 400, params)
                self.assertIn('Filtro de progreso', response.json()['error'])
            for value in (None, True, [], 42):
                with self.assertRaises(web_app.ApiError):
                    self.server.app.progress_payload(value)
            query.assert_not_called()
        self.assertEqual(self.http.get(self.base + '/api/progress', params={'q': 'x' * 100}, timeout=5).status_code, 200)
        self.answer.assert_not_called()

    def test_progress_defaults_remain_available_while_chat_locked_and_hide_stale_data(self):
        self.server.app.lock.acquire()
        try:
            response = self.http.get(self.base + '/api/progress?q=', timeout=5)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data['total_matches'], 150)
            self.assertEqual(len(data['quests']), 40)
            self.assertTrue(data['truncated'])
            self.assertIn('achievementDiaries', data)
            self.monitor._pending = True
            unavailable = self.http.get(self.base + '/api/progress?q=quest', timeout=5).json()
            self.assertFalse(unavailable['ok'])
            self.assertNotIn('quests', unavailable)
            self.assertNotIn('achievementDiaries', unavailable)
        finally:
            self.server.app.lock.release()
        self.answer.assert_not_called()
        self.assertEqual(self.server.app.history, [])

    def test_progress_preserves_http_guards_and_serves_accessible_controls(self):
        for headers in ({'Host': 'rebind.example'}, {'Origin': 'https://external.example'}, {'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.http.get(self.base + '/api/progress?q=quest', headers=headers, timeout=5).status_code, 403)
        response = self.http.get(self.base, timeout=5)
        for name in ('diary-progress', 'progress-search', 'progress-category', 'progress-status', 'progress-results'):
            self.assertIn(f'id="{name}"', response.text)
        self.assertIn("connect-src 'self'", response.headers['Content-Security-Policy'])
        self.answer.assert_not_called()

    def test_retro_theme_csp_allows_only_requested_font_and_image_sources(self):
        response = self.http.get(self.base, timeout=5)
        policy = response.headers['Content-Security-Policy']
        for directive in ("default-src 'self'", "script-src 'self'", "connect-src 'self'",
                          "frame-ancestors 'none'", "base-uri 'none'", "form-action 'self'",
                          "style-src 'self' https://fonts.googleapis.com",
                          "font-src 'self' data: https://fonts.gstatic.com", "img-src 'self' data:"):
            self.assertIn(directive, policy)
        self.assertNotIn('unsafe-inline', policy)
        self.assertNotIn('unsafe-eval', policy)
        for font in ('Pixelify+Sans', 'Chakra+Petch', 'Plus+Jakarta+Sans'):
            self.assertIn(font, response.text)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_quick_filters_and_search_precede_progress_breakdown_and_equipment(self):
        html = self.http.get(self.base, timeout=5).text
        for category, status in (('quests', 'in_progress'), ('quests', 'incomplete'),
                                 ('quests', 'completed'), ('diaries', 'incomplete')):
            self.assertIn(f'data-progress-cat="{category}" data-progress-status="{status}"', html)
        self.assertLess(html.index('id="progress-search"'), html.index('id="diary-progress"'))
        self.assertLess(html.index('id="progress-results"'), html.index('id="combat-progress"'))
        self.assertLess(html.index('id="progress-search"'), html.index('id="equipment"'))
        ids = ('connection','live-freshness','player-name','player-meta','quest-points','gold',
               'tab-state','tab-gear','tab-memory','memory-count','state-content','gear-content',
               'memory-content','skills','patch-count','farming','birdhouses','bank-search',
               'bank-results','equipment','ge-offers','slayer','kill-counts','quest-progress',
               'diary-progress','combat-progress','progress-search','progress-category',
               'progress-status','progress-results','memories','state-path','model-label',
               'model-select','clear','conversation','welcome','error','chat-form','message','send')
        for name in ids:
            self.assertEqual(html.count(f'id="{name}"'), 1, name)
        self.answer.assert_not_called()

    def test_denied_posts_return_complete_403_without_mutation_or_connection_reset(self):
        for _ in range(12):
            response = self.post('/api/chat', {'message': 'Denied example'}, **{'X-CSRF-Token':'wrong'})
            self.assertEqual(response.status_code, 403)
            self.assertIn('error', response.json())
        self.answer.assert_not_called()
        self.assertEqual(self.server.app.history, [])

    def test_manual_notes_create_duplicate_fts_search_and_never_call_model(self):
        note = {'tema': 'Quest Cape', 'contenido': 'Completar Dragon Slayer y entrenar Farming'}
        response = self.post('/api/memories', note)
        self.assertEqual(response.status_code, 200)
        saved = response.json()
        self.assertTrue(saved['saved'])
        duplicate = self.post('/api/memories', note).json()
        self.assertEqual(duplicate, {'saved': False, 'duplicate': True, 'id': saved['id']})
        self.post('/api/memories', {'tema': 'Equipo', 'contenido': 'Example helmet'})
        for query in ('dragon slayer', 'DRAGON farming', 'dragon missing'):
            result = self.http.get(self.base + '/api/memories', params={'q': query}, timeout=5)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['memories'][0]['id'], saved['id'])
        self.assertEqual(self.http.get(self.base + '/api/memories?q=unmatched', timeout=5).json()['memories'], [])
        self.assertEqual(len(self.http.get(self.base + '/api/memories?q=', timeout=5).json()['memories']), 2)
        self.assertEqual(self.server.app.history, [])
        self.answer.assert_not_called()

    def test_manual_notes_validate_limits_csrf_origin_and_busy_lock(self):
        good = {'tema': 'Meta', 'contenido': 'Fictional note'}
        for data in ({}, {'tema':'x'}, {**good, 'extra':1}, {'tema':1,'contenido':'x'},
                     {'tema':'x','contenido':False}, {'tema':' ','contenido':'x'},
                     {'tema':'x'*201,'contenido':'x'}, {'tema':'x','contenido':'x'*8001},
                     {'tema':'x','contenido':'bad\x00note'}):
            self.assertEqual(self.post('/api/memories', data).status_code, 400)
            self.assertFalse(self.server.app.lock.locked())
        for q in ('x'*301, 'bad\x00query'):
            self.assertEqual(self.http.get(self.base + '/api/memories', params={'q':q}, timeout=5).status_code, 400)
        self.assertEqual(self.http.post(self.base + '/api/memories', json=good, timeout=5).status_code, 403)
        self.assertEqual(self.post('/api/memories', good, Origin='https://external.example').status_code, 403)
        self.server.app.lock.acquire()
        try:
            self.assertEqual(self.post('/api/memories', good).status_code, 409)
        finally:
            self.server.app.lock.release()
        with patch.object(web_app, 'save_memory', side_effect=web_app.sqlite3.Error('private path')):
            response = self.post('/api/memories', good)
            self.assertEqual(response.status_code, 502)
            self.assertNotIn('private path', response.text)
        self.assertFalse(self.server.app.lock.locked())
        self.assertEqual(memory_db.list_memories(), [])
        self.answer.assert_not_called()

    def test_direct_ge_and_wiki_use_injected_clients_without_inference_or_history(self):
        for path, client in (('/api/ge', self.ge), ('/api/wiki', self.wiki)):
            response = self.http.get(self.base + path, params={'q':'  Example & item  '}, timeout=5)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), client.return_value)
            client.assert_called_once_with('Example & item')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.server.app.history, [])
        self.answer.assert_not_called()
        self.models.assert_not_called()

    def test_direct_oracle_validates_queries_guards_origin_and_sanitizes_errors(self):
        for path, client in (('/api/ge', self.ge), ('/api/wiki', self.wiki)):
            for q in ('', '  ', 'x'*101, 'bad\x00query'):
                self.assertEqual(self.http.get(self.base + path, params={'q':q}, timeout=5).status_code, 400)
            client.assert_not_called()
            for headers in ({'Host':'rebind.example'}, {'Origin':'https://external.example'}, {'Sec-Fetch-Site':'cross-site'}):
                self.assertEqual(self.http.get(self.base + path + '?q=test', headers=headers, timeout=5).status_code, 403)
            client.side_effect = web_app.WikiError('private diagnostic')
            response = self.http.get(self.base + path + '?q=test', timeout=5)
            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.json(), {'error':'No se pudo consultar OSRS Wiki.'})
            self.assertNotIn('private diagnostic', response.text)
        self.answer.assert_not_called()

    def test_phase6_controls_and_timer_data_preserve_dom_order(self):
        self.monitor._state['timers'] = {'farming':[{'crop':'Example crop','state':'GROWING','readyAt':'2030-01-01T00:00:00Z','stage':2,'stages':5}], 'birdhouses':[]}
        self.monitor._state['dailies'] = {'herbBoxes':{'unlocked':True,'claimed':False,'claimedCount':0,'max':15}}
        data = self.http.get(self.base + '/api/status', timeout=5).json()
        self.assertEqual(data['stats']['timers']['farming']['entries'][0]['stage'], 2)
        self.assertFalse(data['stats']['dailies']['herbBoxes']['claimed'])
        html = self.http.get(self.base, timeout=5).text
        for name in ('dailies','memory-form','memory-topic','memory-text','memory-save','memory-search',
                     'oracle-form','oracle-search','oracle-mode','oracle-submit','oracle-results'):
            self.assertEqual(html.count(f'id="{name}"'), 1)
        self.assertLess(html.index('id="progress-results"'), html.index('id="oracle-form"'))
        self.assertLess(html.index('id="oracle-results"'), html.index('id="equipment"'))
        self.assertLess(html.index('id="memory-form"'), html.index('id="memories"'))
        self.answer.assert_not_called()

    @unittest.skipUnless((web_app.DIST_ROOT / 'index.html').is_file(), 'Compila frontend con npm run build')
    def test_react_bundle_assets_keep_mime_csp_and_session_token_out_of_javascript(self):
        page = self.http.get(self.base, timeout=5)
        self.assertIn('id="root"', page.text)
        self.assertNotIn('@@APP@@', page.text)
        self.assertNotIn('@@CSRF@@', page.text)
        assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', page.text)
        self.assertTrue(any(path.endswith('.js') for path in assets))
        self.assertTrue(any(path.endswith('.css') for path in assets))
        for path in assets:
            result = self.http.get(self.base + path, timeout=5)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.headers['Content-Security-Policy'], page.headers['Content-Security-Policy'])
            self.assertEqual(result.headers['Cache-Control'], 'no-store')
            self.assertNotIn(self.server.app.csrf, result.text)
            self.assertIn('javascript' if path.endswith('.js') else 'text/css', result.headers['Content-Type'])
        self.answer.assert_not_called()

    def test_compiled_assets_reject_traversal_unapproved_types_and_external_origins(self):
        for path in ('/assets/%2e%2e/%2e%2e/auth.py','/assets/..%5c..%5cauth.py','/assets/missing.js','/assets/%00.css','/assets/test.html'):
            self.assertEqual(self.http.get(self.base + path, timeout=5).status_code, 404, path)
        self.assertEqual(self.http.get(self.base + '/assets/missing.js', headers={'Origin':'https://external.example'}, timeout=5).status_code, 403)
        self.answer.assert_not_called()

    def test_legacy_fallback_still_works_without_compiled_frontend(self):
        with patch.object(web_app, 'DIST_ROOT', Path(self.temp.name) / 'unbuilt'):
            response = self.http.get(self.base, timeout=5)
            self.assertEqual(response.status_code, 200)
            self.assertIn(self.server.app.csrf, response.text)
            self.assertIn('src="/app.js"', response.text)
            self.assertEqual(self.http.get(self.base + '/app.js', timeout=5).status_code, 200)


if __name__ == '__main__':
    unittest.main()
