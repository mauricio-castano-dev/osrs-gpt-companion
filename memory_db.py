"""Memoria local FTS5 por tokens: AND primero, OR como alternativa."""
import re
import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / 'memories.sqlite3'


def _connect():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('''CREATE VIRTUAL TABLE IF NOT EXISTS memories USING fts5(
            tema, contenido, created_at UNINDEXED, tokenize='unicode61'
        )''')
        connection.commit()
        return connection
    except BaseException:
        connection.close()
        raise


def _text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or '\x00' in value:
        raise ValueError(f'Se requiere texto no vacio de hasta {maximum} caracteres.')
    return value.strip()


def save_memory(tema, contenido):
    tema, contenido = _text(tema, 200), _text(contenido, 8000)
    with closing(_connect()) as connection, connection:
        connection.execute('BEGIN IMMEDIATE')
        existing = connection.execute(
            'SELECT rowid FROM memories WHERE tema = ? AND contenido = ?', (tema, contenido)
        ).fetchone()
        if existing:
            return {'saved': False, 'duplicate': True, 'id': existing['rowid']}
        cursor = connection.execute(
            "INSERT INTO memories(tema, contenido, created_at) VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            (tema, contenido),
        )
        return {'saved': True, 'id': cursor.lastrowid}


def search_memory(query):
    query = _text(query, 300)
    tokens = re.findall(r'\w+', query, flags=re.UNICODE)
    if not tokens:
        return []
    quoted = ['"' + token.replace('"', '""') + '"' for token in tokens]
    with closing(_connect()) as connection:
        sql = '''SELECT rowid AS id, tema, contenido, created_at FROM memories
                 WHERE memories MATCH ? ORDER BY bm25(memories), rowid DESC LIMIT 8'''
        rows = connection.execute(sql, (' AND '.join(quoted),)).fetchall()
        if not rows and len(quoted) > 1:
            rows = connection.execute(sql, (' OR '.join(quoted),)).fetchall()
        return [dict(row) for row in rows]
