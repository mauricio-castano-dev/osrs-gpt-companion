import { useEffect, useState } from "react";
import { api, errorText } from "@/api/client";
export function useQuery<T>(path: string | null, revision = 0) {
  const [data, set] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!path) {
      set(null);
      setError("");
      setLoading(false);
      return;
    }
    const abort = new AbortController();
    setLoading(true);
    setError("");
    set(null);
    api<T>(path, undefined, abort.signal)
      .then((value) => {
        if (!abort.signal.aborted) set(value);
      })
      .catch((err) => {
        if (!abort.signal.aborted) setError(errorText(err));
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false);
      });
    return () => abort.abort();
  }, [path, revision]);
  return { data, error, loading };
}
