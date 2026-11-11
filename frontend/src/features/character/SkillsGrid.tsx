import { useState } from "react";
import { useApp } from "@/api/AppContext";
import { Section } from "@/components/ui/section";
export function SkillsGrid() {
  const { status, connected } = useApp();
  const [filter, set] = useState("");
  const skills = connected && status?.stats.ok ? status.stats.skills || {} : {};
  return (
    <Section title="Habilidades" icon="stats">
      <input
        aria-label="Filtrar habilidades"
        placeholder="Filtrar habilidad…"
        value={filter}
        onChange={(e) => set(e.target.value)}
      />
      <div id="skills" className="skills-grid">
        {Object.entries(skills)
          .filter(([name]) => name.toLowerCase().includes(filter.toLowerCase()))
          .map(([name, value]) => {
            const level = typeof value === "number" ? value : value.level;
            const normalized = name.toLowerCase().replace(/[^a-z]/g, "");
            const skill =
              normalized === "runecrafting"
                ? "runecraft"
                : normalized === "defense"
                  ? "defence"
                  : normalized;
            return (
              <div
                key={name}
                data-skill={skill}
                className={`skill ${typeof level === "number" && level >= 99 ? "skill-max" : ""}`}
              >
                <span>{name.replaceAll("_", " ")}</span>
                <b>{level ?? "—"}</b>
              </div>
            );
          })}
        {!Object.keys(skills).length && (
          <p className="muted">Sin habilidades disponibles.</p>
        )}
      </div>
    </Section>
  );
}
