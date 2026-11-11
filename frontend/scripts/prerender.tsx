import { readFileSync, writeFileSync } from "node:fs";
import { renderToString } from "react-dom/server";
import { App } from "../src/components/layout/AppShell";
const path = new URL("../dist/index.html", import.meta.url);
const html = readFileSync(path, "utf8");
if (!html.includes("@@APP@@"))
  throw new Error("No se encontró el punto de montaje SSR.");
writeFileSync(path, html.replace("@@APP@@", renderToString(<App />)));
