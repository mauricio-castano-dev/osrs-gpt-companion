import { useApp } from "@/api/AppContext";
import { Section } from "@/components/ui/section";
import { GameIcon } from "@/components/ui/game-icon";
import { number } from "@/lib/format";
const slots: Record<string, string> = {
  HEAD: "head",
  CAPE: "cape",
  AMULET: "neck",
  NECK: "neck",
  WEAPON: "attack",
  BODY: "body",
  SHIELD: "defence",
  LEGS: "legs",
  GLOVES: "hands",
  HANDS: "hands",
  BOOTS: "agility",
  FEET: "agility",
  RING: "ring",
  AMMO: "fletching",
};
export function GearAndSlayer() {
  const { status, connected } = useApp();
  const items = connected && status?.items.ok ? status.items : null,
    stats = connected && status?.stats.ok ? status.stats : null;
  const slayer = stats?.slayer;
  return (
    <div className="gear-secondary">
      <Section title="Equipo actual" icon="equipment" collapsible>
        <div id="equipment">
          {Object.entries(items?.equipment || {})
            .filter(([, item]) => item.name || item.itemId)
            .map(([slot, item]) => (
              <p className="data-row" key={slot}>
                <GameIcon name={slots[slot] || "equipment"} />
                <small>{slot}</small>
                <span>{item.name || `Objeto #${item.itemId}`}</span>
              </p>
            ))}
        </div>
      </Section>
      <Section title="Grand Exchange" icon="ge" collapsible>
        <div id="ge-offers">
          {items?.grandExchange
            ?.filter((item) => item.state !== "EMPTY")
            .map((offer, i) => (
              <article className="progress-entry" key={i}>
                <strong>{offer.name}</strong>
                <small>
                  {offer.state} · {number(offer.quantitySold)}/
                  {number(offer.totalQuantity)} @ {number(offer.price)} GP
                </small>
              </article>
            ))}
        </div>
      </Section>
      <Section title="Slayer & Kill Counts" icon="slayer" collapsible>
        <div id="slayer">
          {slayer ? (
            <>
              <p>
                {slayer.masterName || "Maestro sin registrar"} ·{" "}
                {number(slayer.points)} puntos · Racha {number(slayer.streak)}
              </p>
              {!!slayer.amount && (
                <p>
                  {slayer.creatureName ||
                    slayer.taskName ||
                    `Tarea #${slayer.creatureId ?? "—"}`}{" "}
                  · {number(slayer.amount)} restantes
                </p>
              )}
            </>
          ) : (
            <p className="muted">Sin datos de Slayer.</p>
          )}
        </div>
        <div id="kill-counts" className="tier-grid">
          {Object.entries(stats?.killCounts || {})
            .filter(([name, count]) => name !== "_omitted" && count > 0)
            .sort((a, b) => b[1] - a[1])
            .map(([name, count]) => (
              <p className="data-row" key={name}>
                {name}
                <b>{number(count)}</b>
              </p>
            ))}
        </div>
      </Section>
    </div>
  );
}
