import type { Progress } from "@/types/osrs";
import { number, questStatus, relative } from "@/lib/format";
export function ProgressResults({ data }: { data: Progress }) {
  const diaries = Object.entries(data.achievementDiaries || {}),
    combat = data.combatAchievements?.tasks || [],
    quests = data.quests || [];
  const matches = quests.length + diaries.length + combat.length;
  return (
    <>
      {data.cached && (
        <p className="cache-notice">
          Respaldo parcial del navegador · reporte {relative(data.lastUpdated)}.
          No incluye todo el catálogo; vuelve a consultar con el servidor
          disponible.
        </p>
      )}
      {!data.ok ? (
        <p>Progreso no disponible.</p>
      ) : (
        <>
          {(quests.length ||
            (!diaries.length && !combat.length && data.quests)) && (
            <h3>Misiones · {number(data.total_matches)} coincidencias</h3>
          )}
          {data.truncated && <p className="muted">Primeras 40 misiones.</p>}
          {quests.map((quest, i) => (
            <article
              className={`progress-entry state-${questStatus(quest.state)}`}
              key={i}
            >
              <strong>{quest.displayName || quest.name}</strong>
              <small>{quest.state || "Sin estado"}</small>
            </article>
          ))}
          {diaries.map(([region, diary]) => (
            <section key={region}>
              <h3>{region}</h3>
              <div className="tier-grid">
                {Object.entries(diary.tiers || {}).map(([tier, done]) => (
                  <p className="data-row" key={tier}>
                    {tier}
                    <span>{done ? "Completado" : "Pendiente"}</span>
                  </p>
                ))}
              </div>
              {diary.tasks?.map((task, i) => (
                <p key={i}>
                  [{task.tier}] {task.name} ·{" "}
                  {task.completed ? "Completado" : "Pendiente"}
                </p>
              ))}
              {diary.truncated && (
                <p className="muted">Primeras 30 tareas del diario.</p>
              )}
            </section>
          ))}
          {!!combat.length && (
            <h3>
              Combat Achievements ·{" "}
              {number(data.combatAchievements?.total_matches)} coincidencias
            </h3>
          )}
          {combat.map((task, i) => (
            <article className="progress-entry" key={i}>
              <strong>{task.name}</strong>
              <small>
                {task.tier} · {task.monster} ·{" "}
                {task.completed ? "Completado" : "Pendiente"}
              </small>
            </article>
          ))}
          {data.combatAchievements?.truncated && (
            <p className="muted">Primeras 25 tareas de combate.</p>
          )}
          {!matches && <p>Sin coincidencias para ese filtro.</p>}
        </>
      )}
    </>
  );
}
