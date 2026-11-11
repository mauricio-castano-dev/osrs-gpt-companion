import { useEffect, useState } from "react";
import { api, errorText } from "@/api/client";
import { useApp } from "@/api/AppContext";
import { useQuery } from "@/hooks/useQuery";
import { useDebounce } from "@/hooks/useDebounce";
import { Button } from "@/components/ui/button";
import type { Memory } from "@/types/osrs";
export function NotesSheet({ onCount }: { onCount?: (count: number) => void }) {
  const { busy, notesRevision } = useApp();
  const [topic, setTopic] = useState(""),
    [text, setText] = useState(""),
    [search, setSearch] = useState(""),
    [revision, setRevision] = useState(0),
    [saving, setSaving] = useState(false),
    [feedback, setFeedback] = useState(""),
    [failure, setFailure] = useState("");
  const q = useDebounce(search.trim());
  const { data, error, loading } = useQuery<{ memories: Memory[] }>(
    "/api/memories" + (q ? "?q=" + encodeURIComponent(q) : ""),
    revision + notesRevision,
  );
  useEffect(() => {
    if (data) onCount?.(data.memories.length);
  }, [data, onCount]);
  async function save() {
    if (saving) return;
    setSaving(true);
    setFailure("");
    setFeedback("");
    const draft = { tema: topic, contenido: text };
    try {
      const value = await api<{ duplicate?: boolean }>("/api/memories", draft);
      setTopic((old) => (old === draft.tema ? "" : old));
      setText((old) => (old === draft.contenido ? "" : old));
      setFeedback(
        value.duplicate ? "La nota ya estaba guardada." : "Nota guardada.",
      );
      setRevision((n) => n + 1);
    } catch (err) {
      setFailure(errorText(err));
    } finally {
      setSaving(false);
    }
  }
  async function remove(id: number) {
    try {
      await api("/api/memories/delete", { id });
      setRevision((n) => n + 1);
    } catch (err) {
      setFailure(errorText(err));
    }
  }
  return (
    <section className="feature-card notes-sheet">
      <h2>
        Notas y objetivos <span>({data?.memories.length || 0})</span>
      </h2>
      <p className="muted">
        Objetivos, bloqueos y notas de la cuenta guardados en SQLite local.
      </p>
      <form
        id="memory-form"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <label className="sr-only" htmlFor="memory-topic">
          Tema de la nota
        </label>
        <input
          id="memory-topic"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          maxLength={200}
          placeholder="Tema de la nota…"
          required
        />
        <label className="sr-only" htmlFor="memory-text">
          Contenido de la nota
        </label>
        <textarea
          id="memory-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={8000}
          placeholder="Escribe una nota u objetivo…"
          required
        />
        <Button id="memory-save" disabled={busy || saving} type="submit">
          {saving ? "Guardando…" : "Guardar nota"}
        </Button>
      </form>
      <p role="status" className="muted">
        {feedback}
      </p>
      <label className="sr-only" htmlFor="memory-search">
        Buscar notas guardadas
      </label>
      <input
        id="memory-search"
        type="search"
        maxLength={300}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Filtrar notas guardadas (FTS5)…"
      />
      {(failure || error) && <p role="alert">{failure || error}</p>}
      <div id="memories">
        {loading ? (
          <p>Buscando…</p>
        ) : (
          data?.memories.map((note) => (
            <article className="memory-card" key={note.id}>
              <div>
                <strong>{note.tema}</strong>
                <p>{note.contenido}</p>
                <small>MEMORIA #{note.id}</small>
              </div>
              <Button
                aria-label={`Olvidar memoria ${note.id}: ${note.tema}`}
                variant="ghost"
                disabled={busy}
                onClick={() => void remove(note.id)}
              >
                ✕
              </Button>
            </article>
          ))
        )}
        {!loading && data && !data.memories.length && (
          <p className="muted">
            {q
              ? "Sin notas para esa búsqueda."
              : "No hay notas guardadas todavía."}
          </p>
        )}
      </div>
    </section>
  );
}
