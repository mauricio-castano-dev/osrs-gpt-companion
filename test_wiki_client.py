import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import requests

from wiki_client import MAPPING_TTL, USER_AGENT, WIKI_BUDGET, WikiClient, WikiError


def response(data, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(data).encode('utf-8')
    result._content_consumed = True
    result.headers['Content-Type'] = 'application/json'
    return result


class WikiTests(unittest.TestCase):
    def setUp(self):
        self.client = WikiClient()
        self.addCleanup(self.client.http.close)
        self.mapping = [{'id': 10, 'name': 'Test whip enhanced', 'examine': 'An item', 'limit': 70, 'highalch': 1},
                        {'id': 11, 'name': 'Test whip', 'examine': 'Another item', 'limit': 70, 'highalch': 2}]
        self.price = {'data': {'11': {'high': 100, 'low': 90, 'highTime': 1, 'lowTime': 2}}}

    def assert_public_requests(self, send):
        for call in send.call_args_list:
            request = call.args[0]
            self.assertEqual(request.headers['User-Agent'], USER_AGENT)
            self.assertNotIn('Authorization', request.headers)
            self.assertTrue(request.url.startswith(('https://prices.runescape.wiki/', 'https://oldschool.runescape.wiki/')))
            self.assertEqual(call.kwargs['timeout'], (5, 15))

    def test_prices_exact_first_partial_fields_and_numeric_lookup(self):
        with patch.object(self.client.http, 'send', side_effect=[response(self.mapping), response(self.price), response({'data': {}})]) as send:
            data = self.client.check_ge_price('tEsT wHiP')
            self.assertEqual([r['id'] for r in data['matches']], [11, 10])
            self.assertEqual(data['matches'][0]['high'], 100)
            self.assertIsNone(data['matches'][1]['high'])
            self.assertEqual(set(data['matches'][0]), {'id', 'name', 'examine', 'high', 'low', 'highTime', 'lowTime', 'limit', 'highalch'})
            self.assert_public_requests(send)
            self.assertEqual(parse_qs(urlsplit(send.call_args_list[1].args[0].url).query)['id'], ['11'])
        with patch.object(self.client.http, 'send', return_value=response(self.price)) as send:
            self.assertEqual(self.client.check_ge_price('11')['matches'][0]['id'], 11)
            self.assertEqual(send.call_count, 1)

    def test_mapping_cache_six_hour_ttl_and_five_matches(self):
        mapping = [{'id': i, 'name': f'ore {i}'} for i in range(10)]
        with patch('wiki_client.time.monotonic', return_value=10), patch.object(self.client.http, 'send', side_effect=[response(mapping)] + [response({'data': {}})] * 5) as send:
            result = self.client.check_ge_price('ore')
            self.assertEqual(len(result['matches']), 5)
            self.assertEqual(result['total_matches'], 10)
            self.assertTrue(result['truncated'])
            self.assertEqual(send.call_count, 6)
        with patch('wiki_client.time.monotonic', return_value=10 + MAPPING_TTL - 1), patch.object(self.client.http, 'send') as send:
            self.assertEqual(self.client.check_ge_price('absent')['matches'], [])
            send.assert_not_called()
        with patch('wiki_client.time.monotonic', return_value=10 + MAPPING_TTL), patch.object(self.client.http, 'send', return_value=response(mapping)) as send:
            self.assertEqual(self.client.check_ge_price('absent')['matches'], [])
            self.assertEqual(send.call_count, 1)

    def test_wiki_plain_extract_unicode_budget_and_user_agent(self):
        hits = {'query': {'search': [{'pageid': i, 'title': f'Test Quest {i}'} for i in range(1, 5)]}}
        extract = '<b>Requirements</b> &amp; ' + ('á界"\\\n' * 1000)
        with patch.object(self.client.http, 'send', side_effect=[response(hits), response({'query': {'pages': {'1': {'extract': extract}}}})]) as send:
            result = self.client.search_osrs_wiki('Test Quest')
            self.assertEqual(len(result['results']), 3)
            self.assertTrue(result['extract'].startswith('Requirements &'))
            self.assertNotIn('<b>', result['extract'])
            self.assertLessEqual(len(json.dumps(result, ensure_ascii=False).encode('utf-8')), WIKI_BUDGET)
            self.assertTrue(result['truncated'])
            self.assert_public_requests(send)
            query = parse_qs(urlsplit(send.call_args_list[0].args[0].url).query)
            self.assertEqual(query['srlimit'], ['3'])
            extract_query = parse_qs(urlsplit(send.call_args_list[1].args[0].url).query)
            self.assertEqual(extract_query['explaintext'], ['1'])
            self.assertEqual(extract_query['exchars'], ['2500'])
            self.assertEqual(extract_query['pageids'], ['1'])

    def test_wiki_no_hits_short_extract_and_unavailable_extract(self):
        with patch.object(self.client.http, 'send', return_value=response({'query': {'search': []}})) as send:
            self.assertEqual(self.client.search_osrs_wiki('nothing')['results'], [])
            self.assertEqual(send.call_count, 1)
        hits = {'query': {'search': [{'pageid': 1, 'title': 'Quest'}]}}
        with patch.object(self.client.http, 'send', side_effect=[response(hits), response({'query': {'pages': {'1': {'extract': 'Short text'}}}}), response({'query': {'pages': {'1': {'extract': 'Short text'}}}})]):
            result = self.client.search_osrs_wiki('quest')
            self.assertEqual(result['extract'], 'Short text')
            self.assertFalse(result['truncated'])
        with patch.object(self.client.http, 'send', side_effect=[response(hits), response({'query': {'pages': {'1': {}}}})]):
            with self.assertRaises(WikiError):
                self.client.search_osrs_wiki('quest')

    def test_network_http_api_and_invalid_schema_fail_cleanly(self):
        for outcome in [requests.Timeout(), response({}, 403), response({'error': {'code': 'bad'}}),
                        response({'query': None}), response([])]:
            with patch.object(self.client.http, 'send', side_effect=[outcome]):
                with self.assertRaises(WikiError):
                    self.client.search_osrs_wiki('quest')
        with patch.object(self.client.http, 'send', return_value=response({'not': 'a list'})):
            with self.assertRaises(WikiError):
                self.client.check_ge_price('ore')

    def test_short_intro_expands_sections_follows_redirect_and_preserves_budget(self):
        hits = {'query': {'search': [{'pageid': 1, 'title': 'Quest redirect'}]}}
        short = {'query': {'pages': {'2': {'pageid': 2, 'extract': 'Short introduction.'}}}}
        expanded = 'Requirements: ' + 'á界"\\\n' * 1000
        sections = {'query': {'pages': {'2': {'pageid': 2, 'extract': expanded}}}}
        with patch.object(self.client.http, 'send', side_effect=[response(hits), response(short), response(sections)]) as send:
            result = self.client.search_osrs_wiki('Quest redirect')
            self.assertTrue(result['extract'].startswith('Requirements:'))
            self.assertEqual(send.call_count, 3)
            intro_query = parse_qs(urlsplit(send.call_args_list[1].args[0].url).query)
            full_query = parse_qs(urlsplit(send.call_args_list[2].args[0].url).query)
            self.assertEqual(intro_query['redirects'], ['1'])
            self.assertEqual(full_query['redirects'], ['1'])
            self.assertEqual(full_query['pageids'], ['2'])
            self.assertNotIn('exintro', full_query)
            self.assertEqual(full_query['exchars'], ['2500'])
            self.assertTrue(result['results'][0]['url'].endswith('curid=2'))
            self.assertLessEqual(len(json.dumps(result, ensure_ascii=False).encode('utf-8')), WIKI_BUDGET)
            self.assert_public_requests(send)

    def test_long_intro_skips_expansion_and_short_expansion_never_discards_intro(self):
        hits = {'query': {'search': [{'pageid': 1, 'title': 'Quest'}]}}
        long_intro = {'query': {'pages': {'1': {'extract': 'a' * 250}}}}
        with patch.object(self.client.http, 'send', side_effect=[response(hits), response(long_intro)]) as send:
            self.assertEqual(len(self.client.search_osrs_wiki('quest')['extract']), 250)
            self.assertEqual(send.call_count, 2)
        intro = {'query': {'pages': {'1': {'extract': 'A useful short intro'}}}}
        full = {'query': {'pages': {'1': {'extract': 'Shorter'}}}}
        with patch.object(self.client.http, 'send', side_effect=[response(hits), response(intro), response(full)]):
            self.assertEqual(self.client.search_osrs_wiki('quest')['extract'], 'A useful short intro')

    def test_expansion_api_failure_is_explicit(self):
        hits = {'query': {'search': [{'pageid': 1, 'title': 'Quest'}]}}
        intro = {'query': {'pages': {'1': {'extract': 'Short intro'}}}}
        with patch.object(self.client.http, 'send', side_effect=[response(hits), response(intro), requests.Timeout()]):
            with self.assertRaises(WikiError):
                self.client.search_osrs_wiki('quest')

    def test_empty_intro_can_recover_requirements_from_sections(self):
        hits = {'query': {'search': [{'pageid': 1, 'title': 'Quest'}]}}
        intro = {'query': {'pages': {'1': {'extract': ''}}}}
        full = {'query': {'pages': {'1': {'extract': 'Requirements: example skill level.'}}}}
        with patch.object(self.client.http, 'send', side_effect=[response(hits), response(intro), response(full)]):
            self.assertTrue(self.client.search_osrs_wiki('quest')['extract'].startswith('Requirements:'))


if __name__ == '__main__':
    unittest.main()
