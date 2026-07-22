import { copyFile, mkdir } from "node:fs/promises";

await mkdir("dist/dashboard", { recursive: true });
await Promise.all([
  copyFile("src/dashboard/index.html", "dist/dashboard/index.html"),
  copyFile("src/dashboard/styles.css", "dist/dashboard/styles.css"),
]);
