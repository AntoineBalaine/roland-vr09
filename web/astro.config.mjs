import { defineConfig } from "astro/config";

// A local tool: the dev server (Vite) is the server. It listens on this machine only.
export default defineConfig({
  server: { host: "127.0.0.1", port: 8765 },
  devToolbar: { enabled: false },
});
