"""Servidor de interfaz local: host/origen estrictos, CSRF y herramientas serializadas."""
import ipaddress
import json
import secrets
import socket
import sqlite3
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import requests
from auth import CompanionError
from inference import answer, list_models
from memory_db import list_memories, delete_memory, save_memory, search_memory
from state_monitor import format_relative_time
from tools import ToolRouter
from wiki_client import WikiError, check_ge_price, search_osrs_wiki

UI_ROOT = Path(__file__).resolve().parent / 'ui'
DIST_ROOT = Path(__file__).resolve().parent / 'frontend' / 'dist'
ASSET_TYPES = {'.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
               '.svg': 'image/svg+xml'}
WINDOW_MODES = {'compact': (440, 860), 'wide': (1180, 860)}


class ApiError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class WindowController:
    def __init__(self):
        self._lock = threading.Lock()
        self.native = False
        self.always_on_top = False
        self.mode = 'compact'
        self._window = None

    def attach(self, window):
        with self._lock:
            self._window = window
            self.native = True

    def detach(self):
        with self._lock:
            self._window = None
            self.native = False

    def _state(self):
        width, height = WINDOW_MODES[self.mode]
        return {'native': self.native, 'always_on_top': self.always_on_top,
                'mode': self.mode, 'width': width, 'height': height}

    def state(self):
        with self._lock:
            return self._state()

    def update(self, data):
        if (not isinstance(data, dict) or not data or not set(data) <= {'always_on_top', 'mode'}
                or ('always_on_top' in data and not isinstance(data['always_on_top'], bool))
                or ('mode' in data and data['mode'] not in ('compact', 'wide'))):
            raise ApiError(400, 'Configuración de ventana inválida.')
        with self._lock:
            pin = data.get('always_on_top', self.always_on_top)
            mode = data.get('mode', self.mode)
            try:
                if self._window is not None:
                    if pin != self.always_on_top:
                        self._window.on_top = pin
                    if mode != self.mode:
                        self._window.resize(*WINDOW_MODES[mode])
            except Exception:
                # No confirmar un estado que el sistema operativo no pudo aplicar.
                if self._window is not None and pin != self.always_on_top:
                    try:
                        self._window.on_top = self.always_on_top
                    except Exception:
                        pass
                raise ApiError(502, 'No se pudo cambiar la ventana nativa.') from None
            self.always_on_top = pin
            self.mode = mode
            return 200, {'ok': True, 'window': self._state()}


def allowed_request(client, host, origin, fetch_site, expected):
    try:
        local = ipaddress.ip_address(client).is_loopback
    except ValueError:
        return False
    return (local and host == urlsplit(expected).netloc and origin in (None, expected)
            and fetch_site not in ('cross-site', 'same-site'))


class AppState:
    def __init__(self, monitor, model, router=None, answer_fn=None, models_fn=None, save_settings_fn=None,
                 ge_fn=None, wiki_fn=None, window_controller=None):
        # Importacion diferida: main carga web_app solo al iniciar la interfaz.
        if save_settings_fn is None:
            from main import save_settings
            save_settings_fn = save_settings
        self.monitor = monitor
        self.model = model
        self.router = router if router is not None else ToolRouter(monitor)
        self.answer = answer_fn or answer
        self.models_fn = models_fn or list_models
        self.save_settings_fn = save_settings_fn
        self.ge_fn = ge_fn or check_ge_price
        self.wiki_fn = wiki_fn or search_osrs_wiki
        self.window = window_controller if window_controller is not None else WindowController()
        self.available_models = None
        self.models_lock = threading.Lock()
        self.history = []
        self.lock = threading.Lock()
        self.active_tools = []
        self.tools_lock = threading.Lock()
        self.csrf = secrets.token_urlsafe(32)

    def get_models(self):
        with self.models_lock:
            if self.available_models is None:
                models = self.models_fn()
                self.available_models = [
                    {'slug': m['slug'], 'display_name': m.get('display_name') or m['slug']}
                    for m in models if isinstance(m, dict) and isinstance(m.get('slug'), str)
                    and m['slug'] and len(m['slug']) <= 200 and not any(ord(c) < 32 for c in m['slug'])]
            return [dict(model) for model in self.available_models]

    def change_model(self, data):
        if set(data) != {'model'} or not isinstance(data['model'], str):
            raise ValueError('Se requiere un modelo valido.')
        if not self.lock.acquire(blocking=False):
            return 409, {'error': 'Hay una respuesta en curso. Espera a que termine.'}
        try:
            slug = data['model']
            if not any(model['slug'] == slug for model in self.get_models()):
                raise ValueError('Modelo no disponible.')
            # Persistir primero: un fallo de disco no cambia el modelo activo.
            self.save_settings_fn(model=slug)
            self.model = slug
            return 200, {'ok': True, 'model': self.model}
        finally:
            self.lock.release()

    def freshness(self):
        timestamp = self.monitor.freshness_summary().get('lastUpdated')
        return {'lastUpdated': timestamp, 'freshness': format_relative_time(timestamp)}

    def progress_payload(self, query='', category='all', status='all'):
        if (not isinstance(query, str) or len(query.strip()) > 100 or '\x00' in query
                or category not in ('all', 'quests', 'diaries', 'combat_achievements')
                or status not in ('all', 'completed', 'incomplete', 'in_progress')):
            raise ApiError(400, 'Filtro de progreso inválido: hasta 100 caracteres, categoría y estado válidos.')
        return self.monitor.query_quests_diaries(query.strip(), category, status)

    def ge_payload(self, query=''):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 100 or '\x00' in query:
            raise ApiError(400, 'Indica un objeto de 1 a 100 caracteres.')
        return self.ge_fn(query.strip())

    def wiki_payload(self, query=''):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 100 or '\x00' in query:
            raise ApiError(400, 'Indica una búsqueda de 1 a 100 caracteres.')
        return self.wiki_fn(query.strip())

    def status(self):
        with self.tools_lock:
            busy = self.lock.locked()
            active_tools = [dict(tool) for tool in self.active_tools] if busy else []
        return {'stats': self.monitor.query_stats([], True),
                'items': self.monitor.query_items('', 'all'),
                'quests': self.monitor.query_quests_diaries('', 'all', 'all'),
                **self.freshness(), 'model': self.model, 'state_file': str(self.monitor.path),
                'busy': busy, 'active_tools': active_tools, 'window': self.window.state()}

    def chat(self, message):
        # Una peticion simultanea no debe bloquear silenciosamente y enviar otra inferencia.
        if not self.lock.acquire(blocking=False):
            return 409, {'error': 'Hay una respuesta en curso. Espera a que termine.'}
        try:
            with self.tools_lock:
                self.active_tools = []
            if message == '/limpiar':
                self.history.clear()
                return 200, {'reply': 'Historial limpiado; las memorias guardadas se conservan.',
                             'tools_used': [], **self.freshness()}
            if message.startswith('/'):
                return 400, {'error': 'Usa /limpiar o los controles de estado y memorias de la interfaz.'}
            used = []
            def record_tool(name, ok):
                tool = {'name': name, 'ok': bool(ok)}
                used.append(tool)
                with self.tools_lock:
                    self.active_tools.append(dict(tool))
            reply = self.answer(message, self.model, self.history, self.router,
                                on_tool_call=record_tool)
            self.history.extend([{'role': 'user', 'content': message}, {'role': 'assistant', 'content': reply}])
            self.history = self.history[-12:]
            return 200, {'reply': reply, 'tools_used': used, **self.freshness()}
        finally:
            with self.tools_lock:
                self.active_tools = []
            self.lock.release()


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    def __init__(self, port, app):
        super().__init__(('127.0.0.1', port), Handler)
        self.app = app
        self.origin = f'http://127.0.0.1:{self.server_port}'

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(15)
        return connection, address


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_body(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def json(self, status, value):
        self.send_body(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8'), 'application/json; charset=utf-8')

    def deny(self, message):
        # HTTP/1.0 cierra la conexion tras responder. En Windows, cerrar con un
        # cuerpo pequeno sin consumir puede causar RST y perder el 403 enviado.
        # Solo descartar bytes acotados; nunca interpretarlos ni ejecutar acciones.
        if self.command in ('POST', 'DELETE') and not self.headers.get('Transfer-Encoding'):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if 0 < length <= 65536:
                    self.rfile.read(length)
            except (ValueError, OSError):
                pass
        self.json(403, {'error': message})

    def permitted(self, mutation=False):
        if not allowed_request(self.client_address[0], self.headers.get('Host'), self.headers.get('Origin'),
                               self.headers.get('Sec-Fetch-Site'), self.server.origin):
            self.deny('Origen local no permitido.')
            return False
        if mutation and not secrets.compare_digest(self.headers.get('X-CSRF-Token', '').encode('utf-8'), self.server.app.csrf.encode('ascii')):
            self.deny('Token de sesion invalido. Recarga la pagina.')
            return False
        return True

    def do_GET(self):
        if not self.permitted():
            return
        path = urlsplit(self.path).path
        try:
            if path == '/api/status':
                self.json(200, self.server.app.status())
            elif path == '/api/window':
                self.json(200, {'window': self.server.app.window.state()})
            elif path == '/api/progress':
                params = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                self.json(200, self.server.app.progress_payload(
                    params.get('q', [''])[0], params.get('category', ['all'])[0],
                    params.get('status', ['all'])[0]))
            elif path == '/api/bank':
                q = parse_qs(urlsplit(self.path).query).get('q', [''])[0].strip()
                if len(q) > 100 or '\x00' in q:
                    self.json(400, {'error': 'Busca hasta 100 caracteres, sin caracteres nulos.'})
                    return
                self.json(200, self.server.app.monitor.query_items(q[:100], 'all'))
            elif path == '/api/models':
                models = self.server.app.get_models()
                self.json(200, {'current': self.server.app.model, 'models': models})
            elif path == '/api/memories':
                q = parse_qs(urlsplit(self.path).query, keep_blank_values=True).get('q', [''])[0].strip()
                if len(q) > 300 or '\x00' in q:
                    raise ApiError(400, 'Búsqueda de notas inválida.')
                self.json(200, {'memories': search_memory(q) if q else list_memories(limit=30)})
            elif path == '/api/ge':
                q = parse_qs(urlsplit(self.path).query, keep_blank_values=True).get('q', [''])[0]
                self.json(200, self.server.app.ge_payload(q))
            elif path == '/api/wiki':
                q = parse_qs(urlsplit(self.path).query, keep_blank_values=True).get('q', [''])[0]
                self.json(200, self.server.app.wiki_payload(q))
            elif path.startswith('/assets/'):
                decoded = unquote(path)
                if '\x00' in decoded:
                    self.json(404, {'error': 'Asset no disponible.'})
                    return
                candidate = (DIST_ROOT / decoded.lstrip('/')).resolve()
                if (not candidate.is_relative_to(DIST_ROOT.resolve())
                        or candidate.suffix not in ASSET_TYPES or not candidate.is_file()):
                    self.json(404, {'error': 'Asset no disponible.'})
                    return
                self.send_body(200, candidate.read_bytes(), ASSET_TYPES[candidate.suffix])
            elif path in ('/', '/app.css', '/app.js'):
                name, kind = {'/': ('index.html', 'text/html'), '/app.css': ('app.css', 'text/css'),
                              '/app.js': ('app.js', 'text/javascript')}[path]
                source = DIST_ROOT / name if path == '/' and (DIST_ROOT / name).is_file() else UI_ROOT / name
                data = source.read_text(encoding='utf-8')
                if path == '/' and '@@APP@@' in data:
                    data = (UI_ROOT / 'index.html').read_text(encoding='utf-8')
                if path == '/':
                    data = data.replace('@@CSRF@@', self.server.app.csrf)
                self.send_body(200, data.encode('utf-8'), kind + '; charset=utf-8')
            else:
                self.json(404, {'error': 'Ruta no disponible.'})
        except ApiError as exc:
            self.json(exc.status, {'error': str(exc)})
        except WikiError:
            self.json(502, {'error': 'No se pudo consultar OSRS Wiki.'})
        except (CompanionError, requests.RequestException):
            self.json(502, {'error': 'No se pudo cargar el catalogo de modelos.'})
        except (OSError, sqlite3.Error, ValueError):
            self.json(500, {'error': 'No se pudieron cargar los datos locales.'})

    def do_POST(self):
        self.mutate()

    def do_DELETE(self):
        self.mutate()

    def do_OPTIONS(self):
        self.json(405, {'error': 'Metodo no permitido.'})

    def mutate(self):
        if not self.permitted(mutation=True):
            return
        path = urlsplit(self.path).path
        if path not in ('/api/chat', '/api/memories', '/api/memories/delete', '/api/model', '/api/window') or (self.command == 'DELETE' and path != '/api/memories/delete'):
            self.json(404, {'error': 'Ruta no disponible.'})
            return
        try:
            if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                self.json(415, {'error': 'Se requiere application/json.'})
                return
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 65536 or self.headers.get('Transfer-Encoding'):
                self.json(413, {'error': 'Peticion demasiado grande o vacia.'})
                return
            data = json.loads(self.rfile.read(length).decode('utf-8'))
            if not isinstance(data, dict):
                raise ValueError('Se requiere un objeto JSON.')
            if path == '/api/window':
                status, result = self.server.app.window.update(data)
                self.json(status, result)
            elif path == '/api/model':
                status, result = self.server.app.change_model(data)
                self.json(status, result)
            elif path == '/api/memories':
                if set(data) != {'tema', 'contenido'} or not all(isinstance(data[key], str) for key in ('tema', 'contenido')):
                    raise ValueError('Se requieren tema y contenido de texto.')
                if not self.server.app.lock.acquire(blocking=False):
                    self.json(409, {'error': 'Hay una respuesta en curso. Espera a que termine.'})
                    return
                try:
                    result = save_memory(data['tema'], data['contenido'])
                finally:
                    self.server.app.lock.release()
                self.json(200, result)
            elif path == '/api/memories/delete':
                if set(data) != {'id'}:
                    raise ValueError('Se requiere solo id.')
                if not self.server.app.lock.acquire(blocking=False):
                    self.json(409, {'error': 'Hay una respuesta en curso. Espera a que termine.'})
                    return
                try:
                    result = delete_memory(data['id'])
                finally:
                    self.server.app.lock.release()
                self.json(200, result)
            else:
                message = data.get('message')
                if set(data) != {'message'} or not isinstance(message, str) or not message.strip() or len(message) > 8000:
                    raise ValueError('Escribe un mensaje de hasta 8000 caracteres.')
                status, result = self.server.app.chat(message.strip())
                self.json(status, result)
        except ApiError as exc:
            self.json(exc.status, {'error': str(exc)})
        except (ValueError, UnicodeError, OverflowError):
            self.json(400, {'error': 'Datos de peticion invalidos.'})
        except (CompanionError, requests.RequestException, sqlite3.Error):
            self.json(502, {'error': 'No se pudo completar la consulta. Las memorias ya guardadas se conservan; revisa conexion y permisos.'})
        except OSError:
            self.json(500, {'error': 'No se pudo guardar la configuracion local.'})


def create_server(monitor, model, port=8765, router=None, answer_fn=None, models_fn=None, save_settings_fn=None,
                  ge_fn=None, wiki_fn=None, window_controller=None):
    app = AppState(monitor, model, router, answer_fn, models_fn, save_settings_fn, ge_fn, wiki_fn, window_controller)
    try:
        return LocalServer(port, app)
    except OSError as exc:
        if port and (getattr(exc, 'winerror', None) == 10048 or getattr(exc, 'errno', None) in (98, 10048)):
            return LocalServer(0, app)
        raise


def serve(monitor, model, port=8765, open_browser=True, prefer_native=True):
    with create_server(monitor, model, port) as server:
        print(f'RuneScribe: {server.origin}')
        print('Pulsa Ctrl+C para cerrar el servidor local.')
        if open_browser and prefer_native:
            try:
                import webview
            except Exception:
                webview = None
            if webview is not None:
                worker = threading.Thread(target=server.serve_forever,
                                          kwargs={'poll_interval': 0.2}, daemon=True)
                started = False
                completed = False
                try:
                    worker.start()
                    started = True
                    window = webview.create_window(
                        'RuneScribe · OSRS Companion', server.origin,
                        width=440, height=860, min_size=(360, 580), resizable=True,
                        on_top=False, background_color='#090d16')
                    server.app.window.attach(window)
                    webview.start(gui='edgechromium' if sys.platform == 'win32' else None)
                    completed = True
                except Exception:
                    server.app.window.detach()
                    print('Ventana nativa no disponible; abriendo el navegador.')
                finally:
                    if started:
                        server.shutdown()
                        worker.join(timeout=5)
                if completed:
                    return
        if open_browser:
            webbrowser.open(server.origin)
        server.serve_forever(poll_interval=0.2)
