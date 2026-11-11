export const number = (n: unknown) =>
  typeof n === "number" && Number.isFinite(n)
    ? new Intl.NumberFormat("es-CO").format(n)
    : "—";
export function relative(stamp?: string) {
  const ms = Date.parse(stamp || "");
  if (!Number.isFinite(ms)) return "sin fecha";
  const s = Math.max(0, Math.floor((Date.now() - ms) / 1000));
  return s < 60
    ? `hace ${s} s`
    : s < 3600
      ? `hace ${Math.floor(s / 60)} min`
      : s < 86400
        ? `hace ${Math.floor(s / 3600)} h`
        : `hace ${Math.floor(s / 86400)} d`;
}
export function countdown(stamp?: string, state?: string, now = Date.now()) {
  const ms = Date.parse(stamp || "");
  if (!Number.isFinite(ms) || state === "DEAD") return "";
  if (["HARVESTABLE", "READY", "COMPLETE"].includes(state || "") || ms <= now)
    return "Listo para recoger";
  const s = Math.ceil((ms - now) / 1000);
  return s < 60
    ? `Listo en ${s} s`
    : s < 3600
      ? `Listo en ${Math.floor(s / 60)} min ${s % 60} s`
      : `Listo en ${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
}
export const questStatus = (s?: string) =>
  ({
    finished: "completed",
    completed: "completed",
    in_progress: "in_progress",
    not_started: "incomplete",
    incomplete: "incomplete",
  })[s?.toLowerCase() || ""] || "unknown";
