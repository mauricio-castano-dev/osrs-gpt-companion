import { useApp } from "@/api/AppContext";
export function ThinkingIndicator() {
  const { status, busy } = useApp();
  return busy ? (
    <p role="status" className="thinking">
      {status?.active_tools?.length
        ? "Consultando: " +
          status.active_tools.map((t) => t.name).join(", ") +
          "…"
        : "Preparando respuesta…"}
    </p>
  ) : null;
}
