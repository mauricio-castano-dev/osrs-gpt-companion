import { useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import { useApp } from "@/api/AppContext";
import { Button } from "@/components/ui/button";
import { MessageBubble } from "./MessageBubble";
import { ThinkingIndicator } from "./ThinkingIndicator";
const suggestions = [
  "¿Qué objetivo me recomiendas según mis habilidades?",
  "¿Tengo cultivos listos para recoger?",
  "Recuerda que quiero conseguir la Quest Cape.",
];
export function ChatView() {
  const { messages, ask, busy, error } = useApp();
  const [text, setText] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages, busy]);
  async function send() {
    if (text.trim() && (await ask(text.trim()))) setText("");
  }
  return (
    <section className="chat-panel" aria-label="Consultas a RuneScribe">
      <header>
        <h2>Consultas & Oráculo</h2>
        <span className="caption">Chat con herramientas</span>
      </header>
      <div
        id="conversation"
        className="conversation"
        aria-live="polite"
        aria-relevant="additions"
      >
        {!messages.length && (
          <div id="welcome" className="welcome">
            <h2>RuneScribe</h2>
            <p>
              Consulta misiones, banco, precios del Grand Exchange y la OSRS
              Wiki.
            </p>
            <div className="suggestions">
              {suggestions.map((question, i) => (
                <Button
                  variant="outline"
                  key={question}
                  onClick={() => setText(question)}
                >
                  {
                    [
                      "Siguiente objetivo según mis niveles",
                      "Estado de mis parches de Farming",
                      "Guardar meta: Quest Cape",
                    ][i]
                  }
                </Button>
              ))}
            </div>
          </div>
        )}
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        <ThinkingIndicator />
        <div ref={bottom} />
      </div>
      <p id="error" role="alert" className="error" hidden={!error}>
        {error}
      </p>
      <form
        id="chat-form"
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <label className="sr-only" htmlFor="message">
          Consulta para RuneScribe
        </label>
        <textarea
          id="message"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              void send();
            }
          }}
          maxLength={8000}
          placeholder="Consulta misiones, banco o mecánicas de la Wiki…"
          required
        />
        <Button
          id="send"
          disabled={busy || !text.trim()}
          type="submit"
          aria-label="Enviar mensaje"
        >
          <Send size={17} />
          <span>Enviar</span>
        </Button>
      </form>
      <p className="composer-help">
        Enter para enviar · Shift + Enter para salto de línea
      </p>
    </section>
  );
}
