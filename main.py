import argparse
import json
import os
import sqlite3
import sys
import webbrowser
from pathlib import Path
import requests
from filelock import FileLock, Timeout
from auth import AUTH_DIR, USAGE, CompanionError, atomic_write, host_id, load_profile, login, logout
from inference import answer, list_models
from state_monitor import StateMonitor, default_state_path, format_relative_time
from tools import ToolRouter
from memory_db import list_memories, delete_memory


def supports_ansi():
    if not sys.stdout.isatty() or os.environ.get('TERM') == 'dumb':
        return False
    if sys.platform != 'win32':
        return True
    try:
        import ctypes
        mode = ctypes.c_ulong()
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        return bool(ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)) and mode.value & 4)
    except (AttributeError, OSError):
        return False


def print_freshness(monitor):
    stamp = monitor.freshness_summary().get('lastUpdated')
    text = '  ↳ Instantánea: ' + format_relative_time(stamp)
    print('\033[90m' + text + '\033[0m' if supports_ansi() else text)


def load_settings():
    """Ignora configuracion rota o campos desconocidos, sin alterar credenciales."""
    try:
        with (AUTH_DIR / 'settings.json').open('rb') as file:
            raw = file.read(16_385)
        if len(raw) > 16_384:
            return {}
        data = json.loads(raw.decode('utf-8'))
        if not isinstance(data, dict):
            return {}
        settings = {}
        model = data.get('model')
        if isinstance(model, str) and model.strip() and len(model) <= 200 and not any(ord(c) < 32 for c in model):
            settings['model'] = model
        state_file = data.get('state_file')
        if isinstance(state_file, str) and state_file and len(state_file) <= 4096 and '\x00' not in state_file:
            path = Path(state_file).expanduser()
            if path.is_file():
                settings['state_file'] = str(path.resolve())
        return settings
    except (OSError, ValueError, UnicodeError):
        return {}


def save_settings(*, state_file=None, model=None):
    """El llamador valida el JSON con el monitor y el modelo contra el catalogo."""
    settings = load_settings()
    if state_file is not None:
        path = Path(state_file).expanduser().resolve()
        if not path.is_file():
            raise ValueError('El archivo de estado no existe.')
        settings['state_file'] = str(path)
    if model is not None:
        if not isinstance(model, str) or not model.strip() or len(model) > 200 or any(ord(c) < 32 for c in model):
            raise ValueError('Modelo invalido.')
        settings['model'] = model
    atomic_write(AUTH_DIR / 'settings.json', json.dumps(settings, ensure_ascii=False).encode('utf-8'))


def print_local_state(monitor):
    stats = monitor.query_stats([], True)
    items = monitor.query_items('', 'all')
    print(f'Estado: ok={bool(stats.get("ok") and items.get("ok"))}')
    print('Ultima actualizacion:', stats.get('lastUpdated') or 'desconocida')
    if not stats.get('ok') or not items.get('ok'):
        print('Estado no disponible:', stats.get('error') or items.get('error') or 'actualizacion en curso')
        print('No se muestran datos antiguos como actuales.')
        return
    player = stats.get('player', {})
    print(f'Personaje: {player.get("username", "?")} | Combate: {player.get("combatLevel", "?")} | Mundo: {player.get("world", "?")}')
    currency = items.get('currency', {})
    def gp(source):
        value = currency.get(source)
        return str(value.get('gp_equivalent', '?')) if isinstance(value, dict) else 'desconocido'
    print(f'GP equivalentes (Coins + Platinum tokens): banco={gp("bank")} | inventario={gp("inventory")}')
    timers = stats.get('timers', {})
    farming = timers.get('farming', {}) if isinstance(timers, dict) else {}
    count = farming.get('active_count', 'desconocido') if isinstance(farming, dict) else 'desconocido'
    print(f'Parches activos de farming: {count}')


def local_command(question, monitor):
    """Devuelve True si se resolvio localmente; no modifica el historial del modelo."""
    if question == '/estado':
        print_local_state(monitor)
        return True
    if question == '/memorias':
        memories = list_memories(limit=20)
        if not memories:
            print('No hay memorias guardadas.')
        for memory in memories:
            print(f'[#{memory["id"]}] ({memory["created_at"]}) {memory["tema"]}: {memory["contenido"]}')
        return True
    if question.split(maxsplit=1)[:1] == ['/olvidar']:
        parts = question.split()
        if len(parts) != 2 or not parts[1].isascii() or not parts[1].isdecimal():
            print('Uso: /olvidar ID (entero mayor que cero).')
            return True
        try:
            memory_id = int(parts[1])
            result = delete_memory(memory_id)
        except (ValueError, OverflowError):
            print('ID invalido: usa un entero mayor que cero dentro del rango de SQLite.')
            return True
        print(f'Memoria #{memory_id} eliminada.' if result['deleted'] else f'No existe la memoria #{memory_id}.')
        return True
    return False


def chat(model, monitor):
    router = ToolRouter(monitor)
    print(f'Usando tu plan ChatGPT | Modelo: {model}')
    print(f'Archivo vigilado: {monitor.path}')
    print('El agente puede consultar tu estado y guardar preferencias en SQLite.')
    print('/salir | /estado | /memorias | /olvidar ID | /limpiar | /uso | /logout')
    history = []
    while True:
        question = input('\nTu: ').strip()
        if question == '/salir':
            return
        if question == '/logout':
            logout()
            return
        if question == '/uso':
            webbrowser.open(USAGE)
            continue
        if question == '/limpiar':
            history.clear()
            print('Historial del chat limpiado; las memorias SQLite se conservan.')
            continue
        if not question:
            continue
        try:
            if local_command(question, monitor):
                continue
            if question.startswith('/'):
                print('Comando desconocido. Usa /estado, /memorias o /olvidar ID.')
                continue
            text = answer(question, model, history, router)
            print('Asistente:', text)
            print_freshness(monitor)
            history.extend([{'role': 'user', 'content': question},
                            {'role': 'assistant', 'content': text}])
            history = history[-12:]
        except sqlite3.Error:
            print('No se pudo acceder a la memoria SQLite. Vuelve a intentarlo.')
        except (CompanionError, requests.RequestException, ValueError) as exc:
            print(str(exc) if isinstance(exc, CompanionError) else 'Error de red o respuesta invalida.')
            print('No se reintenta automaticamente. Las memorias guardadas antes del error se conservan.')


def run(default_ui=False, force_ui=False):
    parser = argparse.ArgumentParser(description='Agente OSRS con estado en vivo y memoria local')
    action = parser.add_mutually_exclusive_group()
    for flag in ('init', 'login', 'logout', 'models', 'check-state'):
        action.add_argument('--' + flag, action='store_true')
    parser.add_argument('--model', help='Slug de uno de los modelos disponibles')
    parser.add_argument('--state-file', help='Ruta al JSON de Character Snapshot; reutiliza la ultima ruta valida guardada')
    interface = parser.add_mutually_exclusive_group()
    interface.add_argument('--ui', action='store_true', help='Abrir la interfaz OSRS en el navegador')
    interface.add_argument('--cli', action='store_true', help='Usar el chat de consola')
    parser.add_argument('--port', type=int, default=8765, help='Puerto local de UI; 0 elige uno libre')
    parser.add_argument('--install-path', '--install-shortcut', action='store_true', help='Instalar lanzadores en el PATH del usuario')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('--port debe estar entre 0 y 65535.')
    if force_ui and args.cli:
        parser.error('osrs-companion-ui requiere la interfaz grafica; usa osrs-companion --cli.')
    if args.install_path:
        from launcher import install_path
        folder = install_path()
        print(f'Lanzadores instalados en {folder}')
        print('Abre una terminal nueva y ejecuta osrs-companion o osrs-companion-ui.')
        return
    AUTH_DIR.mkdir(exist_ok=True)
    with FileLock(str(AUTH_DIR / 'session.lock'), timeout=0):
        host_id()
        if args.init:
            print('Instalacion inicializada.')
            return
        if args.logout:
            logout()
            return
        if args.login:
            login()
            print('Token Sharing:', 'chatgpt.tokens.use.direct' in load_profile().get('scope', '').split())
            return
        settings = load_settings()
        state_file = args.state_file or settings.get('state_file') or str(default_state_path())
        if args.check_state:
            with StateMonitor(state_file) as monitor:
                snapshot = monitor.snapshot()
                if not snapshot['ok']:
                    raise CompanionError(snapshot['error'] or 'El archivo se esta actualizando; vuelve a comprobarlo.')
                if args.state_file:
                    save_settings(state_file=monitor.path)
                print(f'Estado valido: {monitor.path}')
            return
        models = list_models()
        if args.models:
            for model in models:
                print(model['slug'], '-', model.get('display_name', model['slug']))
            return
        if args.model and args.model not in {m['slug'] for m in models}:
            raise CompanionError('Modelo no disponible. Consulta --models.')
        available = {m['slug'] for m in models}
        model = args.model or (settings.get('model') if settings.get('model') in available else models[0]['slug'])
        if not args.model and settings.get('model') and settings['model'] not in available:
            print('El modelo guardado no esta disponible; se usara el primero del catalogo.')
        with StateMonitor(state_file) as monitor:
            updates = {}
            if args.state_file and monitor.snapshot().get('ok'):
                updates['state_file'] = monitor.path
            if args.model:
                updates['model'] = model
            if updates:
                save_settings(**updates)
            if force_ui or args.ui or (default_ui and not args.cli):
                from web_app import serve
                serve(monitor, model, port=args.port)
            else:
                chat(model, monitor)


def _entry(default_ui=True, force_ui=False):
    try:
        run(default_ui=default_ui, force_ui=force_ui)
        return 0
    except (KeyboardInterrupt, EOFError):
        print('\nHasta luego.')
        return 0
    except Timeout:
        print('Ya hay una instancia usando esta instalacion.', file=sys.stderr)
    except CompanionError as exc:
        print(str(exc), file=sys.stderr)
    except (requests.RequestException, ValueError, KeyError, OSError):
        print('Error de red o datos locales. Revisa --state-file y la conexion.', file=sys.stderr)
    return 1


def main():
    return _entry()


def run_ui():
    return _entry(force_ui=True)


if __name__ == '__main__':
    raise SystemExit(main())
