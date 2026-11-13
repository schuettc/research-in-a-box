import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["**/dist/", "**/cdk.out/", "**/node_modules/", "docs/", "practice-data/", ".venv/"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["packages/infra/**/*.ts", "*.js"],
    languageOptions: { globals: globals.node },
  },
  {
    files: ["packages/web/**/*.{ts,tsx}"],
    languageOptions: { globals: globals.browser },
    ...reactHooks.configs.flat.recommended,
  },
);
