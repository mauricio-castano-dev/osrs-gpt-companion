import { useApp } from "@/api/AppContext";
import { useClock } from "@/hooks/useClock";
import { countdown } from "@/lib/format";
import type { Activity } from "@/types/osrs";
import { Section } from "@/components/ui/section";
function entries(value: Activity[] | { entries?: Activity[] } | undefined) {
  return Array.isArray(value) ? value : value?.entries || [];
}
function Run({
  item,
  bird = false,
  now,
}: {
  item: Activity;
  bird?: boolean;
  now: number;
}) {
  const text = countdown(item.readyAt, item.state, now || undefined);
  const ready =
    ["HARVESTABLE", "READY", "COMPLETE"].includes(item.state || "") ||
    text === "Listo para recoger";
  return (
    <article
      className={`activity ${item.state === "DEAD" ? "dead" : ready ? "ready" : "growing"}`}
    >
      <strong>
        {bird
          ? `Birdhouse · ${item.house || "Trampa"}`
          : item.crop || item.patch || "Parche"}
      </strong>
      <small>
        {item.patch || item.region || item.space || "Sin ubicación"} ·{" "}
        {item.state || "Sin estado"}
        {typeof item.stage === "number" &&
        typeof item.stages === "number" &&
        item.stages > 0
          ? ` · Etapa ${item.stage}/${item.stages}`
          : ""}
      </small>
      {text && <small className="timer-badge">{text}</small>}
    </article>
  );
}
export function RunsTracker() {
  const { status, connected } = useApp();
  const now = useClock();
  const timers = connected && status?.stats.ok ? status.stats.timers : null;
  const farming = entries(timers?.farming),
    birds = entries(timers?.birdhouses);
  return (
    <Section title="Farming & Birdhouses" icon="farming">
      <span id="patch-count" className="caption">
        {farming.length ? `${farming.length} ACTIVOS` : ""}
      </span>
      <div id="farming">
        {farming.map((item, i) => (
          <Run key={i} item={item} now={now} />
        ))}
      </div>
      <div id="birdhouses">
        {birds.map((item, i) => (
          <Run key={i} item={item} now={now} bird />
        ))}
      </div>
      {!farming.length && !birds.length && (
        <p className="muted">No hay actividades registradas.</p>
      )}
    </Section>
  );
}
