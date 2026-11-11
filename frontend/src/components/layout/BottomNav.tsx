import {
  MessagesSquare,
  UserRound,
  Compass,
  BookOpen,
  NotebookPen,
} from "lucide-react";
import type { Section } from "@/types/osrs";
const links = [
  ["chat", "Chat", MessagesSquare],
  ["state", "Personaje", UserRound],
  ["gear", "Progreso", Compass],
  ["oracle", "Oráculo", BookOpen],
  ["memory", "Notas", NotebookPen],
] as const;
export function BottomNav({
  active,
  navigate,
}: {
  active: Section;
  navigate: (section: Section) => void;
}) {
  return (
    <nav className="bottom-nav" aria-label="Navegación principal">
      {links.map(([section, label, Icon]) => (
        <button
          key={section}
          className={active === section ? "active" : ""}
          aria-current={active === section ? "page" : undefined}
          onClick={() => navigate(section)}
        >
          <Icon size={20} />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}
