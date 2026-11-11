import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { App } from "@/components/layout/AppShell";
import { MessageBubble } from "@/features/chat/MessageBubble";
import { DirectOracle } from "@/features/oracle/DirectOracle";
import { countdown } from "@/lib/format";
import { cachedProgress } from "@/features/progress/cache";
import { api } from "@/api/client";
import type { Status, WindowState } from "@/types/osrs";
vi.mock("@/api/client", async (original) => ({
  ...(await original<typeof import("@/api/client")>()),
  api: vi.fn(),
}));
const status: Status = {
  stats: {
    ok: true,
    player: { username: "Example Player" },
    skills: { ATTACK: 99 },
    dailies: { herbBoxes: { unlocked: true, claimed: false } },
  },
  items: { ok: true },
  quests: {
    ok: true,
    quests: [{ name: "Example quest", state: "IN_PROGRESS" }],
    truncated: true,
  },
  model: "demo",
  state_file: "ExamplePlayer.json",
  busy: false,
};
beforeEach(() => {
  let nativeWindow: WindowState = {
    native: true,
    always_on_top: false,
    mode: "compact",
    width: 440,
    height: 860,
  };
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(async (path, body) => {
    if (path === "/api/status")
      return { ...status, window: nativeWindow } as never;
    if (path === "/api/window") {
      nativeWindow = { ...nativeWindow, ...(body as Partial<WindowState>) };
      return { ok: true, window: nativeWindow } as never;
    }
    if (path === "/api/models")
      return { models: [{ slug: "demo", display_name: "Demo" }] } as never;
    if (path.startsWith("/api/memories"))
      return (body ? { saved: true, id: 1 } : { memories: [] }) as never;
    if (path.startsWith("/api/bank"))
      return {
        ok: true,
        bank: {
          items: [{ name: "Example rune", quantity: 200 }],
          total_matches: 1,
          bank_total_items: 800,
        },
        inventory: [],
      } as never;
    if (path.startsWith("/api/progress"))
      return {
        ok: true,
        quests: [{ name: "Example quest", state: "IN_PROGRESS" }],
        total_matches: 1,
      } as never;
    if (path.startsWith("/api/wiki"))
      return {
        ok: true,
        extract: "Example extract",
        results: [
          {
            title: "Example",
            url: "https://oldschool.runescape.wiki/w/Example",
          },
        ],
      } as never;
    if (path.startsWith("/api/ge")) return { ok: true, matches: [] } as never;
    if (path === "/api/chat")
      return { reply: "Example answer", tools_used: [] } as never;
    return {} as never;
  });
});
describe("RuneScribe modular frontend", () => {
  it("pins and expands the native window using the local window endpoint without model calls", async () => {
    render(<App />);
    await screen.findByText("Example Player");
    const pin = screen.getByRole("button", {
      name: "Fijar ventana siempre visible",
    });
    expect(pin).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(pin);
    await waitFor(() => expect(pin).toHaveAttribute("aria-pressed", "true"));
    expect(vi.mocked(api)).toHaveBeenCalledWith("/api/window", {
      always_on_top: true,
    });
    fireEvent.pointerDown(screen.getByRole("button", { name: "Abrir menú" }), {
      button: 0,
      ctrlKey: false,
    });
    const expand = await screen.findByRole("menuitem", {
      name: "Vista Escritorio (1180px)",
    });
    fireEvent.click(expand);
    await waitFor(() =>
      expect(vi.mocked(api)).toHaveBeenCalledWith("/api/window", {
        mode: "wide",
      }),
    );
    expect(
      vi.mocked(api).mock.calls.some(([path]) => path === "/api/chat"),
    ).toBe(false);
  });
  it("prerenders semantic IDs exactly once without client credentials", () => {
    const html = renderToString(<App />);
    for (const id of [
      "connection",
      "player-name",
      "tab-state",
      "tab-gear",
      "tab-memory",
      "memory-count",
      "bank-search",
      "bank-results",
      "progress-search",
      "diary-progress",
      "combat-progress",
      "equipment",
      "memory-form",
      "oracle-form",
      "chat-form",
      "welcome",
    ])
      expect(html.match(new RegExp(`id="${id}"`, "g"))).toHaveLength(1);
    expect(html.indexOf('id="progress-search"')).toBeLessThan(
      html.indexOf('id="equipment"'),
    );
  });
  it("renders skills and supports mobile section navigation and immediate quest filters", async () => {
    render(<App />);
    await screen.findByText("Example Player");
    const skill = document.querySelector('[data-skill="attack"]');
    expect(skill).toHaveClass("skill-max");
    const nav = within(
      screen.getByRole("navigation", { name: "Navegación principal" }),
    );
    fireEvent.click(nav.getByRole("button", { name: "Progreso" }));
    fireEvent.click(screen.getByRole("button", { name: "En curso" }));
    await waitFor(() =>
      expect(
        vi
          .mocked(api)
          .mock.calls.some(
            ([path]) =>
              path.includes("/api/progress?") &&
              path.includes("status=in_progress"),
          ),
      ).toBe(true),
    );
  });
  it("opens the accessible bank drawer and searches RAM without asking the model", async () => {
    render(<App />);
    await screen.findByText("Example Player");
    fireEvent.click(screen.getByRole("button", { name: "Abrir banco" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByRole("searchbox"), {
      target: { value: "rune" },
    });
    await within(dialog).findByText("Example rune");
    expect(
      vi.mocked(api).mock.calls.some(([path]) => path === "/api/chat"),
    ).toBe(false);
  });
  it("saves a manual note with the existing POST contract and preserves safety", async () => {
    render(<App />);
    await screen.findByText("Example Player");
    fireEvent.click(
      within(
        screen.getByRole("navigation", { name: "Navegación principal" }),
      ).getByRole("button", { name: "Notas" }),
    );
    fireEvent.change(screen.getByLabelText("Tema de la nota"), {
      target: { value: "Meta" },
    });
    fireEvent.change(screen.getByLabelText("Contenido de la nota"), {
      target: { value: "<img src=x>Quest Cape" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar nota" }));
    await screen.findByText("Nota guardada.");
    expect(vi.mocked(api)).toHaveBeenCalledWith("/api/memories", {
      tema: "Meta",
      contenido: "<img src=x>Quest Cape",
    });
    expect(screen.getByLabelText("Contenido de la nota")).toHaveValue("");
    expect(document.querySelectorAll("img")).toHaveLength(0);
  });
  it("renders Markdown as safe React nodes with no images or executable links", () => {
    const { container } = render(
      <MessageBubble
        message={{
          id: 1,
          role: "assistant",
          content:
            "# Heading\n- **Example**\n<img src=x onerror=fake()>\n[bad](javascript:fake())\n![image](https://example.com/x.png)",
        }}
      />,
    );
    expect(container.querySelectorAll("img,script")).toHaveLength(0);
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
    expect(screen.getByText("Example")).toBeInTheDocument();
  });
  it("queries the direct oracle and only exposes Wiki HTTPS links", async () => {
    render(<DirectOracle />);
    fireEvent.change(screen.getByLabelText("Modo de consulta"), {
      target: { value: "wiki" },
    });
    fireEvent.change(
      screen.getByLabelText("Consultar Grand Exchange u OSRS Wiki"),
      { target: { value: "Example & boss" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Consultar" }));
    await screen.findByText("Example extract");
    expect(screen.getByRole("link", { name: "Example" })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
    expect(
      vi
        .mocked(api)
        .mock.calls.some(
          ([path]) => path === "/api/wiki?q=Example%20%26%20boss",
        ),
    ).toBe(true);
  });
  it("keeps countdowns and partial cached progress semantics", () => {
    const now = Date.parse("2030-01-01T00:00:00Z");
    expect(countdown("2030-01-01T00:01:01Z", "GROWING", now)).toBe(
      "Listo en 1 min 1 s",
    );
    expect(countdown("2029-01-01T00:00:00Z", "DEAD", now)).toBe("");
    const result = cachedProgress(
      status.quests,
      "example",
      "quests",
      "in_progress",
    );
    expect(result?.cached).toBe(true);
    expect(result?.quests).toHaveLength(1);
    expect(cachedProgress({ ok: false }, "", "all", "all")).toBeNull();
  });
});
it("submits and clears chat even when scrolling returns a non-cleanup value", async () => {
  const scroll = vi
    .spyOn(Element.prototype, "scrollIntoView")
    .mockImplementation(() => Promise.resolve() as unknown as void);
  try {
    render(<App />);
    await screen.findByText("Example Player");
    fireEvent.change(screen.getByLabelText("Consulta para RuneScribe"), {
      target: { value: "Example question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Enviar mensaje" }));
    await screen.findByText("Example answer");
    expect(screen.getByLabelText("Consulta para RuneScribe")).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: "Limpiar chat" }));
    await waitFor(() =>
      expect(screen.queryByText("Example answer")).not.toBeInTheDocument(),
    );
  } finally {
    scroll.mockRestore();
  }
});
