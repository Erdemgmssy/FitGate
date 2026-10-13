import { defineConfig } from "vite";
export default defineConfig({
  server: { proxy: { "/api": process.env.FITGATE_API_PROXY || "http://127.0.0.1:8001" } },
});
