import argparse
import sys
import webbrowser
import requests
from filelock import FileLock, Timeout
from auth import AUTH_DIR, USAGE, CompanionError, host_id, load_profile, login, logout
from inference import answer, list_models
from state_monitor import StateMonitor, default_state_path
from tools import ToolRouter


def chat(model, monitor):
    router = ToolRouter(monitor)
    print(f'Usando tu plan ChatGPT | Modelo: {model}')
    print(f'Archivo vigilado: {monitor.path}')
    print('El agente puede consultar tu estado y guardar preferencias en SQLite.')
    print('/salir | /limpiar | /uso | /logout')
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
            text = answer(question, model, history, router)
            print('Asistente:', text)
            history.extend([{'role': 'user', 'content': question},
                            {'role': 'assistant', 'content': text}])
            history = history[-12:]
        except (CompanionError, requests.RequestException, ValueError) as exc:
            print(str(exc) if isinstance(exc, CompanionError) else 'Error de red o respuesta invalida.')
            print('No se reintenta automaticamente. Las memorias guardadas antes del error se conservan.')


def run():
    parser = argparse.ArgumentParser(description='Agente OSRS con estado en vivo y memoria local')
    action = parser.add_mutually_exclusive_group()
    for flag in ('init', 'login', 'logout', 'models', 'check-state'):
        action.add_argument('--' + flag, action='store_true')
    parser.add_argument('--model', help='Slug de uno de los modelos disponibles')
    parser.add_argument('--state-file', default=str(default_state_path()), help='Ruta al JSON exportado por RuneLite')
    args = parser.parse_args()
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
        if args.check_state:
            with StateMonitor(args.state_file) as monitor:
                snapshot = monitor.snapshot()
                if not snapshot['ok']:
                    raise CompanionError(snapshot['error'] or 'El archivo se esta actualizando; vuelve a comprobarlo.')
                print(f'Estado valido: {monitor.path}')
            return
        models = list_models()
        if args.models:
            for model in models:
                print(model['slug'], '-', model.get('display_name', model['slug']))
            return
        if args.model and args.model not in {m['slug'] for m in models}:
            raise CompanionError('Modelo no disponible. Consulta --models.')
        with StateMonitor(args.state_file) as monitor:
            chat(args.model or models[0]['slug'], monitor)


if __name__ == '__main__':
    try:
        run()
    except (KeyboardInterrupt, EOFError):
        print('\nHasta luego.')
    except Timeout:
        sys.exit('Ya hay una instancia usando esta instalacion.')
    except CompanionError as exc:
        sys.exit(str(exc))
    except (requests.RequestException, ValueError, KeyError, OSError):
        sys.exit('Error de red o datos locales. Revisa --state-file y la conexion.')
