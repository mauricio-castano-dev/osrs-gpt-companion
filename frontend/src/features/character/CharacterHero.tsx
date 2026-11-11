import { useApp } from "@/api/AppContext";
import { GameIcon } from "@/components/ui/game-icon";
import { number } from "@/lib/format";
export function CharacterHero() {
  const { status, connected } = useApp();
  const player = connected && status?.stats.ok ? status.stats.player : null;
  const money = status?.items.currency;
  return (
    <div className="character-summary">
      <GameIcon name="head" />
      <div>
        <strong id="player-name">
          {player?.username || "Sin personaje activo"}
        </strong>
        <small id="player-meta">
          {player
            ? `Combate ${player.combatLevel ?? "—"} · Mundo ${player.world ?? "—"}`
            : "Character Snapshot no disponible"}
        </small>
      </div>
      <div className="wealth-pills">
        <span>
          <GameIcon name="quests" />
          <b id="quest-points">
            {number(
              connected && status?.stats.ok ? status.stats.questPoints : null,
            )}
          </b>
        </span>
        <span>
          <GameIcon name="coins" />
          <b id="gold">
            {number(
              connected && status?.items.ok && money?.bank && money.inventory
                ? money.bank.gp_equivalent + money.inventory.gp_equivalent
                : null,
            )}
          </b>
        </span>
      </div>
    </div>
  );
}
