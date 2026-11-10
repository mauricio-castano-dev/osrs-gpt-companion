"""Lanzadores de Windows y registro idempotente en el PATH del usuario."""
import ntpath
import os
import sys
from pathlib import Path


def append_user_path(current, directory):
    normalize = lambda value: ntpath.normcase(ntpath.normpath(os.path.expandvars(value.strip(' "'))))
    if any(normalize(part) == normalize(str(directory)) for part in current.split(';') if part.strip()):
        return current
    return current.rstrip(';') + (';' if current.strip(';') else '') + str(directory)


def register_user_path(directory):
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, 'Environment', 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
        try:
            current, kind = winreg.QueryValueEx(key, 'Path')
        except FileNotFoundError:
            current, kind = '', winreg.REG_EXPAND_SZ
        updated = append_user_path(current, directory)
        if updated != current:
            winreg.SetValueEx(key, 'Path', 0, kind, updated)
    os.environ['PATH'] = append_user_path(os.environ.get('PATH', ''), directory)
    try:
        import ctypes
        from ctypes import wintypes
        broadcast = ctypes.windll.user32.SendMessageTimeoutW
        broadcast.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                              wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
        broadcast.restype = wintypes.LPARAM
        text = ctypes.create_unicode_buffer('Environment')
        result = ctypes.c_size_t()
        broadcast(0xFFFF, 0x001A, 0, ctypes.cast(text, ctypes.c_void_p).value, 2, 2000, ctypes.byref(result))
    except (AttributeError, OSError, TypeError, ctypes.ArgumentError):
        pass


def install_path(project_dir=None, bin_dir=None):
    if sys.platform != 'win32':
        raise OSError('El registro de lanzadores en PATH requiere Windows.')
    project = Path(project_dir or Path(__file__).resolve().parent).resolve()
    python = project / '.venv' / 'Scripts' / 'python.exe'
    script = project / 'main.py'
    if not python.is_file() or not script.is_file():
        raise OSError('Crea primero .venv e instala el proyecto con pip install -e .')
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
    bin_path = Path(bin_dir or local / 'OSRSGPTCompanion' / 'bin').resolve()
    bin_path.mkdir(parents=True, exist_ok=True)
    def quote_path(path):
        return '"' + str(path).replace('%', '%%') + '"'
    command = quote_path(python) + ' ' + quote_path(script)
    for directory in (project, bin_path):
        for name, extra in (('osrs-companion.cmd', ''), ('osrs-companion-ui.cmd', ' --ui')):
            (directory / name).write_bytes(('@echo off\r\n' + command + extra + ' %*\r\n').encode('utf-8'))
    register_user_path(bin_path)
    return bin_path
