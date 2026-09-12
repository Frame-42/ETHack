import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { resolve, extname, sep } from "node:path";
import { fileURLToPath } from "node:url";
const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const types = {
  ".html": "text/html",
  ".css": "text/css",
  ".mjs": "text/javascript",
  ".js": "text/javascript",
  ".json": "application/json",
  ".csv": "text/csv",
  ".md": "text/plain",
  ".svg": "image/svg+xml",
};
createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(
      new URL(req.url, "http://localhost").pathname,
    );
    const file = resolve(
      root,
      "." + (pathname === "/" ? "/index.html" : pathname),
    );
    const relative = file.slice(root.length);
    const allowed = ["/index.html", "/src/", "/data/processed/", "/docs/"].some(
      (p) => relative === p || (p.endsWith("/") && relative.startsWith(p)),
    );
    if (
      !file.startsWith(root + sep) ||
      !allowed ||
      !(await stat(file)).isFile()
    ) {
      res.writeHead(404).end("Not found");
      return;
    }
    res.writeHead(200, {
      "Content-Type": `${types[extname(file)] ?? "application/octet-stream"}; charset=utf-8`,
      "Cache-Control": "no-store",
    });
    res.end(await readFile(file));
  } catch {
    res.writeHead(404).end("Not found");
  }
}).listen(Number(process.env.PORT ?? 4173), "127.0.0.1", () =>
  console.log(
    `After the Pledge → http://127.0.0.1:${process.env.PORT ?? 4173}`,
  ),
);
