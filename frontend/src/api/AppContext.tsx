import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, errorText } from "./client";
import type {
  ChatReply,
  Message,
  Model,
  Status,
  WindowState,
} from "@/types/osrs";
interface State {
  status: Status | null;
  connected: boolean;
  busy: boolean;
  error: string;
  setError: (s: string) => void;
  models: Model[];
  messages: Message[];
  ask: (text: string) => Promise<boolean>;
  changeModel: (slug: string) => Promise<void>;
  notesRevision: number;
  windowPending: boolean;
  toggleAlwaysOnTop: () => Promise<void>;
  toggleWindowMode: () => Promise<void>;
}
const Context = createContext<State | null>(null);
export function AppProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null),
    [connected, setConnected] = useState(false),
    [pending, setPending] = useState(false),
    [error, setError] = useState(""),
    [models, setModels] = useState<Model[]>([]),
    [messages, setMessages] = useState<Message[]>([]),
    [notesRevision, setNotes] = useState(0),
    [windowPending, setWindowPending] = useState(false);
  const pendingRef = useRef(false),
    id = useRef(0),
    windowRequest = useRef(false),
    windowRevision = useRef(0);
  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      let fast = pendingRef.current;
      const revision = windowRevision.current;
      try {
        const value = await api<Status>("/api/status", undefined, abort.signal);
        if (abort.signal.aborted) return;
        setStatus((previous) =>
          revision === windowRevision.current
            ? value
            : { ...value, window: previous?.window || value.window },
        );
        setConnected(true);
        fast ||= !!value.busy;
      } catch {
        if (!abort.signal.aborted) setConnected(false);
      }
      if (!abort.signal.aborted) timer = setTimeout(poll, fast ? 600 : 3000);
    }
    void poll();
    return () => {
      abort.abort();
      clearTimeout(timer);
    };
  }, [pending]);
  useEffect(() => {
    const abort = new AbortController();
    api<{ models: Model[] }>("/api/models", undefined, abort.signal)
      .then((data) => {
        if (!abort.signal.aborted) setModels(data.models);
      })
      .catch(() => {});
    return () => abort.abort();
  }, []);
  const busy = pending || !!status?.busy;
  async function ask(text: string) {
    if (pendingRef.current || status?.busy) return false;
    pendingRef.current = true;
    setPending(true);
    setError("");
    if (text !== "/limpiar")
      setMessages((old) => [
        ...old,
        { id: ++id.current, role: "user", content: text },
      ]);
    try {
      const reply = await api<ChatReply>("/api/chat", { message: text });
      if (text === "/limpiar") setMessages([]);
      else
        setMessages((old) => [
          ...old,
          {
            id: ++id.current,
            role: "assistant",
            content: reply.reply,
            ...reply,
          },
        ]);
      setNotes((n) => n + 1);
      setStatus((old) =>
        old ? { ...old, busy: false, active_tools: [] } : old,
      );
      return true;
    } catch (err) {
      setError(errorText(err));
      return false;
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  }
  async function changeModel(model: string) {
    if (busy) return;
    try {
      await api("/api/model", { model });
      setStatus((old) => (old ? { ...old, model } : old));
      setError("");
    } catch (err) {
      setError(errorText(err));
    }
  }
  async function updateWindow(data: Partial<WindowState>) {
    if (windowRequest.current || !status?.window?.native) return;
    windowRequest.current = true;
    windowRevision.current++;
    setWindowPending(true);
    try {
      const result = await api<{ window: WindowState }>("/api/window", data);
      windowRevision.current++;
      setStatus((previous) =>
        previous ? { ...previous, window: result.window } : previous,
      );
      setError("");
    } catch (err) {
      setError(errorText(err));
    } finally {
      windowRequest.current = false;
      setWindowPending(false);
    }
  }
  const toggleAlwaysOnTop = () =>
    updateWindow({ always_on_top: !status?.window?.always_on_top });
  const toggleWindowMode = () =>
    updateWindow({
      mode: status?.window?.mode === "wide" ? "compact" : "wide",
    });
  return (
    <Context.Provider
      value={{
        status,
        connected,
        busy,
        error,
        setError,
        models,
        messages,
        ask,
        changeModel,
        notesRevision,
        windowPending,
        toggleAlwaysOnTop,
        toggleWindowMode,
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useApp() {
  const value = useContext(Context);
  if (!value) throw new Error("AppProvider requerido");
  return value;
}
