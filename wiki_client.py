"""Consultas publicas de OSRS Wiki; nunca reutiliza credenciales de OpenAI."""
import json
import threading
import time
from html import unescape
from html.parser import HTMLParser

import requests

USER_AGENT = 'OSRS-GPT-Companion/1.0 (Local RuneLite Companion; contact: local-user)'
PRICES_API = 'https://prices.runescape.wiki/api/v1/osrs'
WIKI_API = 'https://oldschool.runescape.wiki/api.php'
MAPPING_TTL = 6 * 60 * 60
WIKI_BUDGET = 2500


class WikiError(Exception):
    pass


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(text):
    parser = PlainText()
    parser.feed(str(text))
    return unescape(''.join(parser.parts)).strip()


def utf8_prefix(text, maximum):
    return text.encode('utf-8')[:max(0, maximum)].decode('utf-8', errors='ignore')


class WikiClient:
    def __init__(self):
        self.http = requests.Session()
        self.http.trust_env = False
        self.http.headers.update({'User-Agent': USER_AGENT, 'Accept': 'application/json'})
        self._mapping = None
        self._mapping_at = 0
        self._lock = threading.Lock()

    def _get(self, url, params=None):
        try:
            with self.http.get(url, params=params, timeout=(5, 15), allow_redirects=False) as response:
                if response.status_code != 200:
                    raise WikiError(f'OSRS Wiki devolvio HTTP {response.status_code}; no hay datos verificados.')
                data = response.json()
            if not isinstance(data, (dict, list)) or isinstance(data, dict) and 'error' in data:
                raise WikiError('La API de OSRS Wiki devolvio un error o formato inesperado.')
            return data
        except (requests.RequestException, ValueError):
            raise WikiError('No se pudo consultar OSRS Wiki; revisa la conexion o vuelve a intentar mas tarde.') from None

    def _get_mapping(self):
        with self._lock:
            if self._mapping is None or time.monotonic() - self._mapping_at >= MAPPING_TTL:
                data = self._get(PRICES_API + '/mapping')
                if not isinstance(data, list) or any(not isinstance(item, dict)
                        or not isinstance(item.get('id'), int) or isinstance(item.get('id'), bool)
                        or not isinstance(item.get('name'), str) for item in data):
                    raise WikiError('Catalogo de objetos de OSRS Wiki invalido.')
                self._mapping = data
                self._mapping_at = time.monotonic()
            return self._mapping

    def check_ge_price(self, item_query):
        query = item_query.strip().casefold()
        if not query or len(query) > 300:
            raise ValueError('item_query debe contener entre 1 y 300 caracteres.')
        mapping = self._get_mapping()
        exact = [item for item in mapping if str(item['id']) == query or item['name'].casefold() == query]
        partial = [item for item in mapping if query in item['name'].casefold() and item not in exact]
        matches = exact + partial
        results = []
        for item in matches[:5]:
            latest = self._get(PRICES_API + '/latest', {'id': item['id']})
            if not isinstance(latest, dict) or not isinstance(latest.get('data'), dict):
                raise WikiError('Respuesta de precios invalida.')
            price = latest['data'].get(str(item['id']), {})
            if not isinstance(price, dict):
                raise WikiError('Precio de objeto invalido.')
            results.append({
                'id': item['id'], 'name': item['name'], 'examine': str(item.get('examine', ''))[:500],
                **{key: price.get(key) for key in ('high', 'low', 'highTime', 'lowTime')},
                'limit': item.get('limit'), 'highalch': item.get('highalch'),
            })
        return {'ok': True, 'source': PRICES_API, 'unit': 'GP', 'retrieved_at': time.time(),
                'matches': results, 'total_matches': len(matches), 'truncated': len(matches) > 5,
                'note': 'high/low son precios observados de compra/venta instantanea, no ofertas garantizadas; revisa sus timestamps. null indica dato ausente.'}

    def search_osrs_wiki(self, query):
        query = query.strip()
        if not query or len(query) > 300:
            raise ValueError('query debe contener entre 1 y 300 caracteres.')
        data = self._get(WIKI_API, {'action': 'query', 'list': 'search', 'srsearch': query,
                                    'srlimit': 3, 'format': 'json'})
        query_data = data.get('query') if isinstance(data, dict) else None
        if not isinstance(query_data, dict) or not isinstance(query_data.get('search'), list):
            raise WikiError('Respuesta de busqueda invalida.')
        hits = query_data['search'][:3]
        results = []
        for hit in hits:
            if not isinstance(hit, dict) or not isinstance(hit.get('pageid'), int) or not isinstance(hit.get('title'), str):
                raise WikiError('Resultado de busqueda invalido.')
            title = utf8_prefix(plain(hit['title']), 80)
            results.append({'title': title, 'url': f'https://oldschool.runescape.wiki/?curid={hit["pageid"]}'})
        result = {'ok': True, 'results': results, 'extract': '', 'truncated': False}
        if not hits:
            return result
        extract, page_id = self._extract(hits[0]['pageid'], intro=True)
        if len(extract) < 250:
            expanded, expanded_id = self._extract(page_id, intro=False)
            if len(expanded) > len(extract):
                extract, page_id = expanded, expanded_id
        result['results'][0]['url'] = f'https://oldschool.runescape.wiki/?curid={page_id}'
        result['truncated'] = True
        # Incluye metadatos, enlaces y escapes JSON en el presupuesto completo.
        overhead = len(json.dumps({**result, 'truncated': False}, ensure_ascii=False).encode('utf-8'))
        if overhead > WIKI_BUDGET:
            raise WikiError('Los metadatos de la wiki superan el presupuesto de respuesta.')
        candidate = utf8_prefix(extract, WIKI_BUDGET - overhead)
        result['extract'] = candidate
        while len(json.dumps(result, ensure_ascii=False).encode('utf-8')) > WIKI_BUDGET:
            candidate = candidate[:-1]
            result['extract'] = candidate
        result['truncated'] = candidate != extract or len(extract) >= 2500
        return result

    def _extract(self, page_id, intro):
        params = {'action': 'query', 'prop': 'extracts', 'pageids': page_id,
                  'explaintext': 1, 'exchars': 2500, 'redirects': 1, 'format': 'json'}
        if intro:
            params['exintro'] = 1
        data = self._get(WIKI_API, params)
        query_data = data.get('query') if isinstance(data, dict) else None
        if not isinstance(query_data, dict) or not isinstance(query_data.get('pages'), dict):
            raise WikiError('Respuesta de extracto invalida.')
        # redirects=1 puede cambiar la clave de la pagina respecto al ID buscado.
        pages = query_data['pages']
        if len(pages) != 1:
            raise WikiError('No se pudo identificar una pagina unica para el extracto.')
        key, page = next(iter(pages.items()))
        if not isinstance(page, dict) or 'missing' in page:
            raise WikiError('Pagina de extracto invalida.')
        extract = page.get('extract')
        if not isinstance(extract, str) or (not intro and not extract.strip()):
            raise WikiError('OSRS Wiki no devolvio un extracto verificable de la pagina principal.')
        resolved_id = page.get('pageid', int(key) if str(key).isdecimal() else page_id)
        if not isinstance(resolved_id, int) or resolved_id <= 0:
            raise WikiError('Identificador de pagina invalido.')
        return plain(extract), resolved_id


CLIENT = WikiClient()


def check_ge_price(item_query):
    return CLIENT.check_ge_price(item_query)


def search_osrs_wiki(query):
    return CLIENT.search_osrs_wiki(query)
