import js from "@eslint/js";
import svelte from "eslint-plugin-svelte";
import globals from "globals";

export default [
  { ignores: ["dist/", "node_modules/", "public/", "fixtures/"] },
  js.configs.recommended,
  ...svelte.configs.recommended,
  {
    languageOptions: { globals: { ...globals.browser } },
    rules: { "no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrors: "none" }] },
  },
  { files: ["src/**/*.worker.js"], languageOptions: { globals: { ...globals.worker } } },
  { files: ["scripts/**", "tests/**", "*.config.js"], languageOptions: { globals: { ...globals.node } } },
];
