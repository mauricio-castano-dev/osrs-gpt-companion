import {
  Menu,
  Backpack,
  BookOpen,
  NotebookPen,
  RotateCcw,
  Pin,
  PanelsTopLeft,
} from "lucide-react";
import { useApp } from "@/api/AppContext";
import { useClock } from "@/hooks/useClock";
import { relative } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { CharacterHero } from "@/features/character/CharacterHero";
import { GameIcon } from "@/components/ui/game-icon";
import type { Section } from "@/types/osrs";
export function TopAppBar({
  navigate,
  openBank,
}: {
  navigate: (section: Section) => void;
  openBank: () => void;
}) {
  const {
    status,
    connected,
    busy,
    models,
    ask,
    changeModel,
    windowPending,
    toggleAlwaysOnTop,
    toggleWindowMode,
  } = useApp();
  const native = Boolean(status?.window?.native);
  const pinned = Boolean(status?.window?.always_on_top);
  useClock();
  return (
    <header className="top-app-bar">
      <div className="top-line">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("chat");
          }}
        >
          <GameIcon name="attack" />
          <span>
            Rune<b>Scribe</b>
          </span>
        </a>
        <div
          id="connection"
          className={`connection ${connected && status?.stats.ok ? "online" : ""}`}
          role="status"
        >
          {connected && status?.stats.ok
            ? "Instantánea disponible"
            : connected
              ? "Esperando instantánea"
              : "Sin conexión"}
        </div>
        <small id="live-freshness">
          Reporte:{" "}
          {connected ? relative(status?.lastUpdated) : "sin datos actuales"}
        </small>
        <div className="quick-actions">
          <Button
            className="window-pin"
            variant="outline"
            aria-label="Fijar ventana siempre visible"
            aria-pressed={pinned}
            disabled={!native || windowPending}
            title={
              native ? "Siempre visible" : "Disponible en la ventana nativa"
            }
            onClick={() => void toggleAlwaysOnTop()}
          >
            <Pin size={16} />
          </Button>
          <Button variant="outline" aria-label="Abrir banco" onClick={openBank}>
            <Backpack size={16} />
          </Button>
          <Button
            variant="outline"
            aria-label="Abrir Oráculo"
            onClick={() => navigate("oracle")}
          >
            <BookOpen size={16} />
          </Button>
          <Button
            variant="outline"
            aria-label="Abrir notas"
            onClick={() => navigate("memory")}
          >
            <NotebookPen size={16} />
          </Button>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" aria-label="Abrir menú">
              <Menu size={20} />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>Ventana</DropdownMenuLabel>
            <DropdownMenuItem
              disabled={!native || windowPending}
              onSelect={() => void toggleAlwaysOnTop()}
            >
              <Pin size={16} />
              {pinned ? "Desfijar ventana" : "Fijar siempre visible"}
            </DropdownMenuItem>
            <DropdownMenuItem
              disabled={!native || windowPending}
              onSelect={() => void toggleWindowMode()}
            >
              <PanelsTopLeft size={16} />
              {status?.window?.mode === "wide"
                ? "Vista Sidekick móvil (440px)"
                : "Vista Escritorio (1180px)"}
            </DropdownMenuItem>
            {!native && (
              <p className="file-path">
                Controles disponibles en la ventana nativa.
              </p>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Accesos</DropdownMenuLabel>
            <DropdownMenuItem onSelect={openBank}>Abrir banco</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => navigate("oracle")}>
              Ver Oráculo
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => navigate("memory")}>
              Ver notas
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Archivo conectado</DropdownMenuLabel>
            <p className="file-path">{status?.state_file || "Sin archivo"}</p>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <CharacterHero />
      <div className="model-controls">
        <span id="model-label">
          {status ? "Modelo: " + status.model : "Cargando modelo…"}
        </span>
        <select
          id="model-select"
          aria-label="Seleccionar modelo"
          hidden={!models.length}
          value={status?.model || ""}
          disabled={busy}
          onChange={(e) => void changeModel(e.target.value)}
        >
          {!status?.model && <option value="">Cargando…</option>}
          {models.map((model) => (
            <option key={model.slug} value={model.slug}>
              {model.display_name}
            </option>
          ))}
        </select>
        <Button
          id="clear"
          variant="ghost"
          size="sm"
          disabled={busy}
          onClick={() => void ask("/limpiar")}
        >
          <RotateCcw size={13} />
          Limpiar chat
        </Button>
        <p id="state-path" className="sr-only">
          {status?.state_file || "Sin archivo conectado"}
        </p>
      </div>
    </header>
  );
}
