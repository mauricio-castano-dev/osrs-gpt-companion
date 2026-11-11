import { useState } from "react";
import { useApp } from "@/api/AppContext";
import { useDebounce } from "@/hooks/useDebounce";
import { useQuery } from "@/hooks/useQuery";
import { Section } from "@/components/ui/section";
import { Button } from "@/components/ui/button";
import type { Progress } from "@/types/osrs";
import { number } from "@/lib/format";
import { cachedProgress } from "./cache";
import { ProgressResults } from "./ProgressResults";
const quick = [
  ["En curso", "quests", "in_progress"],
  ["Misiones pendientes", "quests", "incomplete"],
  ["Misiones completadas", "quests", "completed"],
  ["Diarios pendientes", "diaries", "incomplete"],
];
export function ProgressExplorer() {
  const { status, connected } = useApp();
  const [search, setSearch] = useState(""),
    [category, setCategory] = useState("all"),
    [filter, setFilter] = useState("all");
  const q = useDebounce(search.trim());
  const active = !!q || category !== "all" || filter !== "all";
  const result = useQuery<Progress>(
    active
      ? `/api/progress?q=${encodeURIComponent(q)}&category=${category}&status=${filter}`
      : null,
  );
  const fallback = result.error
    ? cachedProgress(status?.quests, q, category, filter)
    : null;
  const data = result.data || fallback;
  const summary = connected && status?.quests.ok ? status.quests : null;
  return (
    <Section title="Misiones & Logros" icon="quests">
      <label className="sr-only" htmlFor="progress-search">
        Filtrar misiones, diarios o logros de combate
      </label>
      <input
        id="progress-search"
        type="search"
        maxLength={100}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Buscar misión, región o jefe…"
      />
      <div className="quick-filters">
        {quick.map(([label, cat, state]) => (
          <Button
            variant="outline"
            size="sm"
            key={label}
            data-progress-cat={cat}
            data-progress-status={state}
            onClick={() => {
              setCategory(cat);
              setFilter(state);
            }}
          >
            {label}
          </Button>
        ))}
      </div>
      <div className="filter-row">
        <select
          id="progress-category"
          aria-label="Categoría de progreso"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="all">Todo</option>
          <option value="quests">Misiones</option>
          <option value="diaries">Diarios</option>
          <option value="combat_achievements">Combat Achievements</option>
        </select>
        <select
          id="progress-status"
          aria-label="Estado de progreso"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">Todos los estados</option>
          <option value="in_progress">En curso</option>
          <option value="incomplete">Pendientes</option>
          <option value="completed">Completados</option>
        </select>
      </div>
      <div id="progress-results" role="status" className="result-stack">
        {!active ? (
          <p className="muted">
            Escribe o elige un filtro para consultar misiones, diarios o logros
            de combate.
          </p>
        ) : result.loading ? (
          <p>Consultando progreso…</p>
        ) : data ? (
          <ProgressResults data={data} />
        ) : result.error ? (
          <p>{result.error}</p>
        ) : null}
      </div>
      <div id="quest-progress" className="summary-line">
        {summary
          ? `${number(summary.finished_count)} completadas · ${number(summary.in_progress_count)} en curso · ${number(summary.not_started_count)} pendientes`
          : "Progreso no disponible."}
      </div>
      <Section title="Achievement Diaries" icon="diaries" collapsible>
        <div id="diary-progress" className="tier-grid">
          {Object.entries(summary?.achievementDiaries || {}).map(
            ([region, diary]) => (
              <p className="data-row" key={region}>
                <span>{region}</span>
                <b>
                  {Object.values(diary.tiers || {}).filter(Boolean).length}/
                  {Object.keys(diary.tiers || {}).length}
                </b>
              </p>
            ),
          )}
        </div>
      </Section>
      <Section title="Combat Achievements" icon="combat" collapsible>
        <div id="combat-progress" className="tier-grid">
          {Object.entries(summary?.combatAchievements?.tiers || {}).map(
            ([tier, counts]) => (
              <p className="data-row" key={tier}>
                {tier}
                <b>
                  {number(counts.completed)} / {number(counts.total)}
                </b>
              </p>
            ),
          )}
        </div>
      </Section>
    </Section>
  );
}
