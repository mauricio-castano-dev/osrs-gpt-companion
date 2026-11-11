import { watch } from "node:fs";
import { spawn } from "node:child_process";
let child = null,
  queued = false,
  timer;
function build() {
  if (child) {
    queued = true;
    return;
  }
  child = spawn(process.execPath, [process.env.npm_execpath, "run", "build"], {
    stdio: "inherit",
    windowsHide: true,
  });
  child.on("exit", () => {
    child = null;
    if (queued) {
      queued = false;
      build();
    }
  });
}
function queue() {
  clearTimeout(timer);
  timer = setTimeout(build, 300);
}
watch("src", { recursive: true }, queue);
for (const file of ["index.html", "vite.config.ts", "tsconfig.json"])
  watch(file, queue);
build();
