"""Filtros sobre personajes ficticios grandes; nunca leer disco por consulta."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import memory_db
import tools
from state_monitor import StateMonitor


def fixture():
    return {
        'schemaVersion': 2, 'lastUpdated': '2026-11-09T00:00:00Z',
        'sectionUpdated': {'bank': '2026-11-08T23:59:00Z'},
        'player': {'username': 'ExamplePlayer', 'combatLevel': 90, 'accountType': 'NORMAL',
                   'members': True, 'spellbook': 'STANDARD', 'unlockedPrayers': ['private-extra']},
        'skills': {'ATTACK': {'level': 77, 'xp': 1500000, 'boostedLevel': 77}, 'slayer': 65},
        'vitals': {'hitpoints': 70}, 'questPoints': 120,
        'slayer': {'points': 150, 'masterName': 'Nieve'},
        'timers': {'birdhouses': list(range(100)), 'farming': list(range(100))},
        'dailies': {'herbBoxes': 0}, 'toolLeprechaunTotals': {'ultracompost': 400},
        'bank': {'totalItems': 802, 'tabs': ['never-export-this'], 'items': [
            {'itemId': index + 2000, 'name': f'Test ore {index}', 'quantity': index + 1}
            for index in range(800)] + [
            {'itemId': 995, 'name': 'Coins', 'quantity': 1234},
            {'itemId': 13204, 'name': 'Platinum token', 'quantity': 2}]},
        'inventory': [{'slot': 0, 'itemId': 995, 'name': 'Coins', 'quantity': 10},
                      {'slot': 1, 'itemId': 554, 'name': 'Fire rune', 'quantity': 500}],
        'equipment': {'WEAPON': {'itemId': 1333, 'name': 'Rune scimitar', 'quantity': 1}},
        'quests': [{'name': f'QUEST_{i}', 'displayName': f'Quest {i}',
                    'state': ('FINISHED', 'IN_PROGRESS', 'NOT_STARTED')[i % 3]} for i in range(150)],
        'achievementDiaries': {
            'ARDOUGNE': {'easy': True, 'medium': False, 'hard': False, 'elite': False,
                         'tasks': {'easy': [{'name': f'Task {i}', 'completed': i < 40} for i in range(80)]}},
            'LUMBRIDGE': {'easy': True, 'medium': False, 'hard': False, 'elite': False,
                         'tasks': {'medium': [{'name': 'Special altar', 'completed': False}]}},
        },
    }


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.monitor = StateMonitor(Path('unused.json'))
        self.monitor._state = fixture()
        self.monitor._pending = False
        self.monitor._error = None
        self.monitor._loaded_at = 100

    def test_stats_case_insensitive_filters_and_compact_timers(self):
        with patch.object(Path, 'open', side_effect=AssertionError('No disk per query')):
            result = self.monitor.query_stats(['attack'], False)
            self.assertEqual(set(result['skills']), {'ATTACK'})
            self.assertEqual(result['player']['username'], 'ExamplePlayer')
            self.assertNotIn('unlockedPrayers', result['player'])
            self.assertNotIn('bank', result)
            self.assertNotIn('timers', result)
            self.assertEqual(result['lastUpdated'], fixture()['lastUpdated'])
            result = self.monitor.query_stats([], True)
            self.assertEqual(result['skills']['slayer'], 65)
            self.assertEqual(result['timers']['birdhouses']['total'], 100)
            self.assertLessEqual(len(result['timers']['birdhouses']['entries']), 12)
            self.assertIn('toolLeprechaunTotals', result)

    def test_bank_blank_search_never_returns_items(self):
        result = self.monitor.query_items('', 'all')
        self.assertNotIn('items', result['bank'])
        self.assertEqual(result['bank']['bank_total_items'], 802)
        self.assertEqual(result['currency']['bank']['gp_equivalent'], 3234)
        self.assertEqual(result['currency']['inventory']['coins'], 10)
        self.assertEqual(len(result['inventory']), 2)
        self.assertIn('WEAPON', result['equipment'])
        self.assertNotIn('tabs', result['bank'])
        self.assertLess(len(json.dumps(result)), 1500)

    def test_bank_limits_and_numeric_ids(self):
        result = self.monitor.query_items('TEST ORE', 'bank')
        self.assertEqual(result['bank']['total_matches'], 800)
        self.assertEqual(len(result['bank']['items']), 30)
        self.assertTrue(result['bank']['truncated'])
        self.assertNotIn('inventory', result)
        result = self.monitor.query_items('2002', 'bank')
        self.assertEqual([i['itemId'] for i in result['bank']['items']], [2002])
        self.assertEqual(self.monitor.query_items('does not exist', 'bank')['bank']['total_matches'], 0)
        self.assertEqual(self.monitor.query_items('rune', 'inventory')['inventory'][0]['itemId'], 554)
        self.assertEqual(self.monitor.query_items('different', 'equipment')['equipment']['WEAPON']['itemId'], 1333)

    def test_currency_absent_and_inventory_bounded(self):
        self.monitor._state.pop('bank')
        self.monitor._state['inventory'] *= 30
        result = self.monitor.query_items('', 'all')
        self.assertIsNone(result['currency']['bank'])
        self.assertEqual(len(result['inventory']), 28)

    def test_quests_status_counts_and_limits(self):
        for status, raw in [('completed', 'FINISHED'), ('incomplete', 'NOT_STARTED'), ('in_progress', 'IN_PROGRESS')]:
            result = self.monitor.query_quests_diaries('', 'quests', status)
            self.assertEqual(result['total_matches'], 50)
            self.assertEqual(len(result['quests']), 40)
            self.assertTrue(result['truncated'])
            self.assertTrue(all(q['state'] == raw for q in result['quests']))
            self.assertEqual([result[k] for k in ('finished_count', 'in_progress_count', 'not_started_count')], [50, 50, 50])
        result = self.monitor.query_quests_diaries('qUeSt 149', 'quests', 'incomplete')
        self.assertEqual(len(result['quests']), 1)
        self.monitor._state['quests'] = {'Old quest': 'completed', 'New quest': 'not_started'}
        self.assertEqual(self.monitor.query_quests_diaries('OLD', 'quests', 'completed')['finished_count'], 1)

    def test_diaries_do_not_dump_tasks_without_specific_search(self):
        result = self.monitor.query_quests_diaries('', 'diaries', 'all')
        self.assertNotIn('quests', result)
        self.assertNotIn('tasks', result['achievementDiaries']['ARDOUGNE'])
        result = self.monitor.query_quests_diaries('ardougne', 'diaries', 'incomplete')
        diary = result['achievementDiaries']['ARDOUGNE']
        self.assertEqual(len(diary['tasks']), 30)
        self.assertEqual(diary['total_matches'], 40)
        self.assertTrue(all(not task['completed'] for task in diary['tasks']))
        self.assertTrue(diary['tiers']['easy'])
        result = self.monitor.query_quests_diaries('special ALTAR', 'diaries', 'all')
        self.assertEqual(list(result['achievementDiaries']), ['LUMBRIDGE'])
        self.assertEqual(len(result['achievementDiaries']['LUMBRIDGE']['tasks']), 1)

    def test_no_stale_data_from_any_query_and_no_shared_mutations(self):
        result = self.monitor.query_stats([], False)
        result['skills']['ATTACK']['level'] = -1
        self.assertEqual(self.monitor.query_stats([], False)['skills']['ATTACK']['level'], 77)
        for pending, error in [(True, None), (False, 'Broken JSON')]:
            self.monitor._pending, self.monitor._error = pending, error
            for result in [self.monitor.query_stats([], True), self.monitor.query_items('', 'all'),
                           self.monitor.query_quests_diaries('', 'all', 'all')]:
                self.assertFalse(result['ok'])
                self.assertEqual(set(result), {'ok', 'pending', 'error', 'loaded_at', 'lastUpdated', 'sectionUpdated'})
                self.assertIsNone(result['lastUpdated'])


class RouterTests(unittest.TestCase):
    def call(self, router, name, **args):
        return router.execute({'namespace': 'osrs', 'name': name, 'arguments': json.dumps(args)})

    def test_exactly_seven_strict_schemas(self):
        expected = {'query_player_stats', 'query_player_bank', 'query_quests_and_diaries',
                    'check_ge_price', 'search_osrs_wiki', 'save_agent_memory', 'recall_agent_memory'}
        self.assertEqual({t['name'] for t in tools.FUNCTION_TOOLS}, expected)
        self.assertEqual(len(tools.FUNCTION_TOOLS), 7)
        for tool in tools.FUNCTION_TOOLS:
            self.assertTrue(tool['strict'])
            self.assertFalse(tool['parameters']['additionalProperties'])
            self.assertEqual(set(tool['parameters']['required']), set(tool['parameters']['properties']))

    def test_all_seven_routes_and_no_full_snapshot(self):
        monitor = Mock()
        monitor.query_stats.return_value = {'ok': True, 'skills': {}}
        monitor.query_items.return_value = {'ok': True, 'bank': {}}
        monitor.query_quests_diaries.return_value = {'ok': True, 'quests': []}
        router = tools.ToolRouter(monitor)
        with tempfile.TemporaryDirectory() as folder, patch.object(memory_db, 'DB_PATH', Path(folder) / 'memory.db'):
            self.assertTrue(self.call(router, 'query_player_stats', skills=['attack'], include_slayer_and_timers=True)['ok'])
            self.assertTrue(self.call(router, 'query_player_bank', search_term='rune', source='bank')['ok'])
            self.assertTrue(self.call(router, 'query_quests_and_diaries', search_term='', category='all', status_filter='all')['ok'])
            self.assertTrue(self.call(router, 'save_agent_memory', tema='Birdhouse', contenido='Quiero hacer runs diarios')['saved'])
            self.assertEqual(len(self.call(router, 'recall_agent_memory', query='Birdhouse')['matches']), 1)
            with patch.object(tools, 'check_ge_price', return_value={'ok': True}) as price:
                self.assertTrue(self.call(router, 'check_ge_price', item_query='Whip')['ok'])
                price.assert_called_once_with(item_query='Whip')
            with patch.object(tools, 'search_osrs_wiki', return_value={'ok': True}) as wiki:
                self.assertTrue(self.call(router, 'search_osrs_wiki', query='Quest')['ok'])
                wiki.assert_called_once_with(query='Quest')
        monitor.snapshot.assert_not_called()
        monitor.query_stats.assert_called_once_with(['attack'], True)

    def test_typed_validation_rejects_extra_missing_enum_array_and_bool(self):
        router = tools.ToolRouter(Mock())
        bad = [
            ('query_player_stats', {'skills': 'attack', 'include_slayer_and_timers': False}),
            ('query_player_stats', {'skills': [7], 'include_slayer_and_timers': False}),
            ('query_player_stats', {'skills': [], 'include_slayer_and_timers': 1}),
            ('query_player_stats', {'skills': []}),
            ('query_player_bank', {'search_term': '', 'source': 'all', 'path': 'secret'}),
            ('query_player_bank', {'search_term': '', 'source': 'disk'}),
            ('query_quests_and_diaries', {'search_term': '', 'category': 'all', 'status_filter': 'wrong'}),
            ('check_ge_price', {'item_query': 995}),
        ]
        for name, args in bad:
            self.assertFalse(self.call(router, name, **args)['ok'])


class MemoryTokenTests(unittest.TestCase):
    def test_and_precedence_or_fallback_unicode_and_safe_operators(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(memory_db, 'DB_PATH', Path(folder) / 'memory.db'):
            a = memory_db.save_memory('Dragon planning', 'Quiero completar Slayer despues de entrenar.')
            memory_db.save_memory('Dragon only', 'Otra meta')
            memory_db.save_memory('Árboles', 'Preparar runs de pájaros')
            self.assertEqual([row['id'] for row in memory_db.search_memory('Dragon Slayer')], [a['id']])
            self.assertEqual(len(memory_db.search_memory('Dragon absent')), 2)
            self.assertEqual(len(memory_db.search_memory('árboles pájaros')), 1)
            self.assertEqual(memory_db.search_memory('" OR 1=1 --'), [])
            self.assertEqual(memory_db.search_memory('*** ---'), [])
            self.assertEqual(len(memory_db.search_memory('dragon OR slayer')), 2)
            for i in range(12):
                memory_db.save_memory(f'Quest {i}', 'Quiero quest cape')
            self.assertEqual(len(memory_db.search_memory('quest')), 8)


if __name__ == '__main__':
    unittest.main()
