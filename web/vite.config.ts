import { defineConfig } from "vite";
export default defineConfig({
  publicDir: "pages-assets",
  server: { host: "0.0.0.0", proxy: { "/api": process.env.PT_LOCAL_API_TARGET || "http://127.0.0.1:8000" } },
});
