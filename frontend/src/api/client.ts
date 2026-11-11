export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  if (!path.startsWith("/api/")) throw new Error("Ruta local no válida.");
  const token =
    typeof document === "undefined"
      ? ""
      : document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')
          ?.content || "";
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    cache: "no-store",
    signal,
    headers:
      body === undefined
        ? {}
        : { "Content-Type": "application/json", "X-CSRF-Token": token },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data: unknown = await response.json();
  if (!response.ok)
    throw new ApiError(
      typeof data === "object" && data && "error" in data
        ? String(data.error)
        : "No se pudo completar la petición.",
      response.status,
    );
  return data as T;
}
export const errorText = (error: unknown) =>
  error instanceof Error ? error.message : "No se pudo completar la petición.";
