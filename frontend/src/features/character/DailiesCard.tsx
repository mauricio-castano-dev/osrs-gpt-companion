import { useApp } from "@/api/AppContext";
import { Section } from "@/components/ui/section";
import type { Daily } from "@/types/osrs";
import { number } from "@/lib/format";
const names: Record<string, string> = {
  herbBoxes: "Cajas de hierbas",
  battlestaves: "Battlestaves",
  sand: "Arena",
  pureEssence: "Esencia pura",
  bonemeal: "Bonemeal",
  dynamite: "Dinamita",
  ogreArrows: "Flechas de ogro",
  bowstrings: "Cuerdas de arco",
  randomRunes: "Runas aleatorias",
};
export function DailiesCard() {
  const { status, connected } = useApp();
  const data = connected && status?.stats.ok ? status.stats.dailies || {} : {};
  const entries = Object.entries(data).filter(
    (entry): entry is [string, Daily] =>
      typeof entry[1] === "object" &&
      entry[1] !== null &&
      (entry[1] as Daily).unlocked === true,
  );
  return (
    <Section title="Dailies" icon="diaries" collapsible open>
      <div id="dailies">
        {entries.map(([name, daily]) => (
          <article
            className={`activity ${daily.claimed === false ? "ready" : "growing"}`}
            key={name}
          >
            <strong>{Object.hasOwn(names, name) ? names[name] : name}</strong>
            <small>
              {daily.claimed === false
                ? "Pendiente hoy"
                : daily.claimed === true
                  ? "Reclamado"
                  : "Sin estado"}
              {typeof daily.claimedCount === "number" &&
              typeof daily.max === "number"
                ? ` · ${number(daily.claimedCount)} / ${number(daily.max)}`
                : ""}
            </small>
          </article>
        ))}
        {!entries.length && (
          <p className="muted">No hay dailies desbloqueadas registradas.</p>
        )}
      </div>
    </Section>
  );
}
