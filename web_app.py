"""Servidor de interfaz local: host/origen estrictos, CSRF y herramientas serializadas."""
import ipaddress
import json
import secrets
import socket
import sqlite3
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import requests
from auth import CompanionError
from inference import answer
from memory_db import list_memories, delete_memory
from state_monitor import format_relative_time
from tools import ToolRouter

UI_ROOT = Path(__file__).resolve().parent / 'ui'


def allowed_request(client, host, origin, fetch_site, expected):
    try:
        local = ipaddress.ip_address(client).is_loopback
    except ValueError:
        return False
    return (local and host == urlsplit(expected).netloc and origin in (None, expected)
            and fetch_site not in ('cross-site', 'same-site'))


class AppState:
    def __init__(self, monitor, model, router=None, answer_fn=None):
        self.monitor = monitor
        self.model = model
        self.router = router if router is not None else ToolRouter(monitor)
        self.answer = answer_fn or answer
        self.history = []
        self.lock = threading.Lock()
        self.csrf = secrets.token_urlsafe(32)

    def freshness(self):
        timestamp = self.monitor.freshness_summary().get('lastUpdated')
        return {'lastUpdated': timestamp, 'freshness': format_relative_time(timestamp)}

    def status(self):
        return {'stats': self.monitor.query_stats([], True),
                'items': self.monitor.query_items('', 'all'),
                'quests': self.monitor.query_quests_diaries('', 'all', 'all'),
                **self.freshness(), 'model': self.model, 'state_file': str(self.monitor.path)}

    def chat(self, message):
        # Una peticion simultanea no debe bloquear silenciosamente y enviar otra inferencia.
        if not self.lock.acquire(blocking=False):
            return 409, {'error': 'Hay una respuesta en curso. Espera a que termine.'}
        try:
            if message == '/limpiar':
                self.history.clear()
                return 200, {'reply': 'Historial limpiado; las memorias guardadas se conservan.',
                             'tools_used': [], **self.freshness()}
            if message.startswith('/'):
                return 400, {'error': 'Usa /limpiar o los controles de estado y memorias de la interfaz.'}
            used = []
            reply = self.answer(message, self.model, self.history, self.router,
                                on_tool_call=lambda name, ok: used.append({'name': name, 'ok': bool(ok)}))
            self.history.extend([{'role': 'user', 'content': message}, {'role': 'assistant', 'content': reply}])
            self.history = self.history[-12:]
            return 200, {'reply': reply, 'tools_used': used, **self.freshness()}
        finally:
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
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def json(self, status, value):
        self.send_body(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8'), 'application/json; charset=utf-8')

    def permitted(self, mutation=False):
        if not allowed_request(self.client_address[0], self.headers.get('Host'), self.headers.get('Origin'),
                               self.headers.get('Sec-Fetch-Site'), self.server.origin):
            self.json(403, {'error': 'Origen local no permitido.'})
            return False
        if mutation and not secrets.compare_digest(self.headers.get('X-CSRF-Token', '').encode('utf-8'), self.server.app.csrf.encode('ascii')):
            self.json(403, {'error': 'Token de sesion invalido. Recarga la pagina.'})
            return False
        return True

    def do_GET(self):
        if not self.permitted():
            return
        path = urlsplit(self.path).path
        try:
            if path == '/api/status':
                self.json(200, self.server.app.status())
            elif path == '/api/memories':
                self.json(200, {'memories': list_memories(limit=30)})
            elif path in ('/', '/app.css', '/app.js'):
                name, kind = {'/': ('index.html', 'text/html'), '/app.css': ('app.css', 'text/css'),
                              '/app.js': ('app.js', 'text/javascript')}[path]
                data = (UI_ROOT / name).read_text(encoding='utf-8')
                if path == '/':
                    data = data.replace('@@CSRF@@', self.server.app.csrf)
                self.send_body(200, data.encode('utf-8'), kind + '; charset=utf-8')
            else:
                self.json(404, {'error': 'Ruta no disponible.'})
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
        if path not in ('/api/chat', '/api/memories/delete') or (self.command == 'DELETE' and path != '/api/memories/delete'):
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
            if path == '/api/memories/delete':
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
        except (ValueError, UnicodeError, OverflowError):
            self.json(400, {'error': 'Datos de peticion invalidos.'})
        except (CompanionError, requests.RequestException, sqlite3.Error):
            self.json(502, {'error': 'No se pudo completar la consulta. Las memorias ya guardadas se conservan; revisa conexion y permisos.'})


def create_server(monitor, model, port=8765, router=None, answer_fn=None):
    app = AppState(monitor, model, router, answer_fn)
    try:
        return LocalServer(port, app)
    except OSError as exc:
        if port and (getattr(exc, 'winerror', None) == 10048 or getattr(exc, 'errno', None) in (98, 10048)):
            return LocalServer(0, app)
        raise


def serve(monitor, model, port=8765, open_browser=True):
    with create_server(monitor, model, port) as server:
        print(f'OSRS GPT Companion: {server.origin}')
        print('Pulsa Ctrl+C para cerrar el servidor local.')
        if open_browser:
            webbrowser.open(server.origin)
        server.serve_forever(poll_interval=0.2)
