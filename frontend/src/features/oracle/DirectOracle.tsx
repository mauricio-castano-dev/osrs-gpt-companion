import { useState } from "react";
import { Section } from "@/components/ui/section";
import { Button } from "@/components/ui/button";
import { useQuery } from "@/hooks/useQuery";
import type { GE, Wiki } from "@/types/osrs";
import { number, relative } from "@/lib/format";
export function DirectOracle() {
  const [text, setText] = useState(""),
    [mode, setMode] = useState("ge"),
    [query, setQuery] = useState<{
      q: string;
      mode: string;
      id: number;
    } | null>(null);
  const { data, error, loading } = useQuery<GE | Wiki>(
    query ? `/api/${query.mode}?q=${encodeURIComponent(query.q)}` : null,
    query?.id,
  );
  function reset() {
    setQuery(null);
  }
  const stamp = (n?: number | null) =>
    typeof n === "number" && Number.isFinite(new Date(n * 1000).getTime())
      ? relative(new Date(n * 1000).toISOString())
      : "sin fecha";
  return (
    <Section title="Oráculo GE & Wiki" icon="wiki">
      <form
        id="oracle-form"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(
            text.trim() ? { q: text.trim(), mode, id: Date.now() } : null,
          );
        }}
      >
        <label className="sr-only" htmlFor="oracle-search">
          Consultar Grand Exchange u OSRS Wiki
        </label>
        <input
          id="oracle-search"
          type="search"
          maxLength={100}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            reset();
          }}
          placeholder="Objeto o artículo…"
        />
        <div className="filter-row">
          <select
            id="oracle-mode"
            aria-label="Modo de consulta"
            value={mode}
            onChange={(e) => {
              setMode(e.target.value);
              reset();
            }}
          >
            <option value="ge">Precios GE</option>
            <option value="wiki">OSRS Wiki</option>
          </select>
          <Button id="oracle-submit" type="submit" disabled={loading}>
            Consultar
          </Button>
        </div>
      </form>
      <div id="oracle-results" className="result-stack" role="status">
        {!query ? (
          <p className="muted">
            Consulta precios en vivo del Grand Exchange o extractos de la OSRS
            Wiki sin usar el modelo.
          </p>
        ) : loading ? (
          <p>Consultando OSRS Wiki…</p>
        ) : error ? (
          <p>{error}</p>
        ) : data && "matches" in data ? (
          <>
            {!data.matches.length && (
              <p>Sin coincidencias en Grand Exchange.</p>
            )}
            {data.matches.map((item, i) => (
              <article className="oracle-card" key={i}>
                <strong>{item.name}</strong>
                <p>
                  Compra inst.: {number(item.high)} GP · Venta inst.:{" "}
                  {number(item.low)} GP
                </p>
                <small>
                  Límite 4h: {number(item.limit)} · High Alch:{" "}
                  {number(item.highalch)} GP
                </small>
                <small>
                  Compra: {stamp(item.highTime)} · Venta: {stamp(item.lowTime)}
                </small>
              </article>
            ))}
            {!!data.matches.length && (
              <p className="muted">
                Precios observados; no son ofertas garantizadas.
              </p>
            )}
          </>
        ) : data && "results" in data ? (
          <>
            {data.extract && <p className="wiki-extract">{data.extract}</p>}
            {data.results
              .filter((item) =>
                item.url.startsWith("https://oldschool.runescape.wiki/"),
              )
              .map((item, i) => (
                <a
                  key={i}
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {item.title}
                </a>
              ))}
            {!data.results.length && <p>Sin resultados en OSRS Wiki.</p>}
            {data.truncated && (
              <p className="muted">
                Extracto abreviado; consulta la página para ver el detalle.
              </p>
            )}
          </>
        ) : null}
      </div>
    </Section>
  );
}
