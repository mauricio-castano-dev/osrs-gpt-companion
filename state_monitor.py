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
        self._lock = threading.Lock()
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
