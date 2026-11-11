import { hydrateRoot } from "react-dom/client";
import { App } from "@/components/layout/AppShell";
import "@/styles/globals.css";
import "@/styles/sprites.css";
const root = document.getElementById("root")!;
hydrateRoot(root, <App />);
