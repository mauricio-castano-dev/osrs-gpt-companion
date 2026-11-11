import ReactMarkdown from "react-markdown";
import type { Message } from "@/types/osrs";
import { relative } from "@/lib/format";
import { GameIcon } from "@/components/ui/game-icon";
const icons: Record<string, string> = {
  query_player_stats: "stats",
  query_player_bank: "bank",
  query_quests_and_diaries: "quests",
  check_ge_price: "ge",
  search_osrs_wiki: "wiki",
  save_agent_memory: "memory",
  recall_agent_memory: "recall",
};
export function MessageBubble({ message }: { message: Message }) {
  return (
    <article className={`message-bubble ${message.role}`}>
      <small>{message.role === "user" ? "Tú" : "RuneScribe"}</small>
      <div className="markdown">
        {message.role === "assistant" ? (
          <ReactMarkdown
            skipHtml
            components={{
              img: () => null,
              a: ({ href, children }) =>
                href && /^https?:\/\//i.test(href) ? (
                  <a href={href} target="_blank" rel="noopener noreferrer">
                    {children}
                  </a>
                ) : (
                  <span>{children}</span>
                ),
            }}
          >
            {message.content}
          </ReactMarkdown>
        ) : (
          message.content
        )}
      </div>
      {message.tools_used && (
        <div className="tool-chips">
          {message.tools_used.map((tool, i) => (
            <span key={i} className={tool.ok ? "" : "failed"}>
              <GameIcon name={icons[tool.name] || "quests"} />
              {tool.name}
              {tool.ok ? "" : " · sin datos"}
            </span>
          ))}
        </div>
      )}
      {message.lastUpdated && (
        <small className="muted">
          Reporte: {relative(message.lastUpdated)}
        </small>
      )}
    </article>
  );
}
