"""Cache de RuneLite actualizada por watchdog, sin lecturas por turno."""
import copy
import json
import os
import threading
import time
from pathlib import Path
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


def default_state_path():
    exported = Path.home() / '.runelite' / 'osrs-companion' / 'kpn_hooligan.json'
    return exported if exported.exists() else Path(__file__).parent / 'kpn_hooligan.json'


class StateMonitor(FileSystemEventHandler):
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self._lock = threading.RLock()
        self._reload = threading.Event()
        self._stop = threading.Event()
        self._state = None
        self._error = 'Todavia no se ha cargado el archivo.'
        self._pending = True
        self._loaded_at = None
        self._observer = Observer()
        self._worker = threading.Thread(target=self._run, daemon=True)

    def on_any_event(self, event):
        if event.is_directory or event.event_type not in ('modified', 'created', 'moved', 'deleted'):
            return
        paths = (event.src_path, getattr(event, 'dest_path', ''))
        if any(p and os.path.normcase(os.path.abspath(p)) == os.path.normcase(str(self.path)) for p in paths):
            with self._lock:
                self._pending = True
            self._reload.set()

    def _load(self):
        try:
            with self.path.open('rb') as file:
                before = os.fstat(file.fileno())
                raw = file.read(1_048_577)
                after = os.fstat(file.fileno())
            current = self.path.stat()
            if (before.st_mtime_ns, before.st_size, before.st_ino) != (after.st_mtime_ns, after.st_size, after.st_ino) or (
                after.st_mtime_ns, after.st_size, after.st_ino
            ) != (current.st_mtime_ns, current.st_size, current.st_ino):
                raise ValueError('El archivo cambio durante la lectura.')
            if len(raw) > 1_048_576:
                raise ValueError('El archivo supera 1 MiB.')
            state = json.loads(raw.decode('utf-8-sig'))
            if not isinstance(state, dict):
                raise ValueError('La raiz JSON debe ser un objeto.')
            json.dumps(state, allow_nan=False)
        except (OSError, ValueError, UnicodeError) as exc:
            with self._lock:
                self._error = f'No se pudo cargar el estado ({type(exc).__name__}).'
                self._pending = self._reload.is_set()
            return False
        with self._lock:
            self._state = state
            self._loaded_at = time.time()
            self._error = None
            self._pending = self._reload.is_set()
        return True

    def _run(self):
        while not self._stop.is_set():
            if not self._reload.wait(0.2):
                continue
            self._reload.clear()
            for delay in (0.1, 0.2, 0.5, 1.0):
                if self._stop.wait(delay):
                    return
                if self._load():
                    break

    def snapshot(self):
        with self._lock:
            ok = self._state is not None and not self._pending and self._error is None
            return {
                'ok': ok, 'pending': self._pending, 'error': self._error,
                'loaded_at': self._loaded_at,
                'data': copy.deepcopy(self._state) if ok else None,
                'note': 'Instantanea del ultimo archivo exportado; no garantiza que RuneLite siga conectado. Consulta lastUpdated y sectionUpdated.',
            }

    def _meta_or_error(self):
        """RLock permite invocarlo dentro de una consulta atomica en memoria."""
        with self._lock:
            ok = self._state is not None and not self._pending and self._error is None
            state = self._state if ok else {}
            return {
                'ok': ok, 'pending': self._pending, 'error': self._error,
                'loaded_at': self._loaded_at,
                'lastUpdated': state.get('lastUpdated'),
                'sectionUpdated': copy.deepcopy(state.get('sectionUpdated', {})),
            }

    def query_stats(self, skills_filter, include_slayer_and_timers):
        with self._lock:
            result = self._meta_or_error()
            if not result['ok']:
                return result
            state = self._state
            player = state.get('player', {})
            wanted = {name.casefold() for name in skills_filter}
            skills = {}
            for name, value in state.get('skills', {}).items():
                if not wanted or name.casefold() in wanted:
                    skills[name] = project(value, ('level', 'xp', 'boostedLevel')) if isinstance(value, dict) else value
            result.update(player=project(player, ('username', 'combatLevel', 'accountType', 'members', 'spellbook')),
                          skills=skills, vitals=compact(state.get('vitals', {})),
                          questPoints=state.get('questPoints'))
            if include_slayer_and_timers:
                for key in ('slayer', 'dailies', 'toolLeprechaunTotals', 'timers'):
                    result[key] = compact(state.get(key, {}))
            return copy.deepcopy(result)

    def query_items(self, search_term, source):
        if source not in ('all', 'bank', 'inventory', 'equipment'):
            raise ValueError('source invalido.')
        with self._lock:
            result = self._meta_or_error()
            if not result['ok']:
                return result
            state = self._state
            bank = state.get('bank', {})
            bank_items = bank.get('items', [])
            inventory = state.get('inventory', [])
            term = search_term.strip().casefold()
            def matches(item):
                return not term or (str(item.get('itemId')) == term if term.isdecimal()
                                    else term in str(item.get('name', '')).casefold())
            result['currency'] = {
                'bank': currency(bank_items) if 'items' in bank else None,
                'inventory': currency(inventory) if 'inventory' in state else None,
            }
            if source in ('all', 'bank'):
                found = [item for item in bank_items if matches(item)] if term else []
                result['bank'] = {
                    'bank_total_items': bank.get('totalItems', len(bank_items)),
                    'total_matches': len(found) if term else None,
                    'truncated': len(found) > 30,
                }
                if term:
                    result['bank']['items'] = [project(item, ITEM_FIELDS) for item in found[:30]]
                else:
                    result['bank']['note'] = 'Indica un nombre o itemId para buscar en el banco; no se lista completo.'
            if source in ('all', 'inventory'):
                result['inventory'] = [project(item, ITEM_FIELDS) for item in inventory[:28] if matches(item)]
            if source in ('all', 'equipment'):
                result['equipment'] = {slot: project(item, ITEM_FIELDS) for slot, item in state.get('equipment', {}).items()}
            return copy.deepcopy(result)

    def query_quests_diaries(self, search_term, category, status_filter):
        if category not in ('all', 'quests', 'diaries') or status_filter not in ('all', 'completed', 'incomplete', 'in_progress'):
            raise ValueError('category o status_filter invalido.')
        with self._lock:
            result = self._meta_or_error()
            if not result['ok']:
                return result
            state = self._state
            raw_quests = state.get('quests', [])
            quests = ([{'name': name, 'state': value} for name, value in raw_quests.items()]
                      if isinstance(raw_quests, dict) else raw_quests)
            counts = {'completed': 0, 'in_progress': 0, 'incomplete': 0}
            for quest in quests:
                status = quest_status(quest.get('state'))
                if status in counts:
                    counts[status] += 1
            result.update(finished_count=counts['completed'], in_progress_count=counts['in_progress'],
                          not_started_count=counts['incomplete'], questPoints=state.get('questPoints'))
            term = search_term.strip().casefold()
            if category in ('all', 'quests'):
                found = [quest for quest in quests
                         if (not term or any(term in str(quest.get(key, '')).casefold() for key in ('name', 'displayName')))
                         and (status_filter == 'all' or quest_status(quest.get('state')) == status_filter)]
                result.update(quests=[project(q, ('name', 'displayName', 'state')) for q in found[:40]],
                              total_matches=len(found), truncated=len(found) > 40)
            if category in ('all', 'diaries'):
                diaries = {}
                for region, diary in state.get('achievementDiaries', {}).items():
                    region_match = bool(term) and term in region.casefold()
                    tasks = [(tier, task) for tier in TIERS for task in diary.get('tasks', {}).get(tier, [])]
                    task_matches = [(tier, task) for tier, task in tasks if term and term in str(task.get('name', '')).casefold()]
                    if term and not region_match and not task_matches:
                        continue
                    tiers = {tier: diary[tier] for tier in TIERS if tier in diary}
                    matching_tiers = tiers
                    if status_filter != 'all':
                        matching_tiers = {tier: done for tier, done in tiers.items()
                                 if (status_filter == 'completed' and done is True)
                                 or (status_filter == 'incomplete' and done is False)}
                    details = tasks if region_match else task_matches
                    details = [(tier, task) for tier, task in details if status_filter == 'all'
                               or (status_filter == 'completed' and task.get('completed') is True)
                               or (status_filter == 'incomplete' and task.get('completed') is False)]
                    if status_filter != 'all' and not matching_tiers and not details:
                        continue
                    entry = {'tiers': tiers}
                    if region_match or task_matches:
                        entry.update(tasks=[{'tier': tier, **project(task, ('name', 'completed'))} for tier, task in details[:30]],
                                     total_matches=len(details), truncated=len(details) > 30)
                    diaries[region] = entry
                result['achievementDiaries'] = diaries
            return copy.deepcopy(result)

    def __enter__(self):
        if not self.path.parent.is_dir():
            raise FileNotFoundError(f'No existe la carpeta: {self.path.parent}')
        self._observer.schedule(self, str(self.path.parent), recursive=False)
        self._observer.start()
        try:
            self._load()
            self._worker.start()
        except BaseException:
            self._observer.stop()
            self._observer.join()
            raise
        return self

    def __exit__(self, *args):
        self._observer.stop()
        self._observer.join()
        self._stop.set()
        self._reload.set()
        self._worker.join()


ITEM_FIELDS = ('slot', 'itemId', 'name', 'quantity')
TIERS = ('easy', 'medium', 'hard', 'elite')


def project(value, fields):
    return {key: value[key] for key in fields if key in value} if isinstance(value, dict) else {}


def compact(value, depth=0):
    """Resumen acotado de extras: como maximo 12 entradas por nivel y profundidad 3."""
    if isinstance(value, dict):
        if depth >= 3:
            return {'count': len(value)}
        items = list(value.items())
        result = {k: compact(v, depth + 1) for k, v in items[:12]}
        if len(items) > 12:
            result['_omitted'] = len(items) - 12
        return result
    if isinstance(value, list):
        return {'count': len(value)} if depth >= 3 else {
            'entries': [compact(v, depth + 1) for v in value[:12]],
            'total': len(value), 'truncated': len(value) > 12,
        }
    return value[:300] if isinstance(value, str) else value


def currency(items):
    coins = platinum = 0
    for item in items:
        name = str(item.get('name', '')).casefold()
        quantity = item.get('quantity', 0)
        if not isinstance(quantity, int) or isinstance(quantity, bool):
            continue
        if item.get('itemId') == 995 or name == 'coins':
            coins += quantity
        elif item.get('itemId') == 13204 or name in ('platinum token', 'platinum tokens'):
            platinum += quantity
    return {'coins': coins, 'platinum_tokens': platinum, 'gp_equivalent': coins + platinum * 1000}


def quest_status(value):
    normalized = str(value).casefold()
    return {'finished': 'completed', 'completed': 'completed',
            'in_progress': 'in_progress', 'not_started': 'incomplete', 'incomplete': 'incomplete'}.get(normalized, 'unknown')
