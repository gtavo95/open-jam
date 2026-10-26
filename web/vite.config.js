import { createReadStream, statSync } from "node:fs";
import { join, normalize, resolve, sep } from "node:path";
import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// En desarrollo (y `vite preview`) sirve lo que exporta Python en /data/ sin copiarlo al
// build: en producción los datos van aparte y la página los busca en VITE_DATA_URL.
const DATOS = resolve(process.env.DATOS_DIR ?? join(import.meta.dirname, "..", "viz", "data"));
const TIPOS = { ".json": "application/json", ".bin": "application/octet-stream" };

function datosLocales() {
  const servir = (req, res, next) => {
    const ruta = decodeURIComponent((req.url ?? "").split("?")[0]);
    if (!ruta.startsWith("/data/")) return next();
    const archivo = normalize(join(DATOS, ruta.slice("/data/".length)));
    if (!archivo.startsWith(DATOS + sep)) return next();
    let info;
    try {
      info = statSync(archivo);
    } catch {
      info = null;
    }
    if (!info?.isFile()) {
      res.statusCode = 404;
      return res.end(`${ruta} no existe en ${DATOS}`);
    }
    res.setHeader("Content-Type", TIPOS[archivo.slice(archivo.lastIndexOf("."))] ?? "application/octet-stream");
    res.setHeader("Content-Length", info.size);
    res.setHeader("Cache-Control", "no-cache");
    if (req.method === "HEAD") return res.end();
    createReadStream(archivo).pipe(res);
  };
  return {
    name: "datos-locales",
    configureServer: (s) => void s.middlewares.use(servir),
    configurePreviewServer: (s) => void s.middlewares.use(servir),
  };
}

export default defineConfig({
  plugins: [svelte(), datosLocales()],
  worker: { format: "es" },
  test: { include: ["tests/**/*.test.js"], environment: "node" },
});
