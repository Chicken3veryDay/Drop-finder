import { resolveFeatureModules } from "./featureRegistryCore";

const discoveredModules = import.meta.glob(
  [
    "../features/*/index.ts",
    "../features/*/index.tsx",
    "../features/*/index.js",
    "../features/*/index.jsx",
    "../features/*/index.mjs",
    "../features/*/register-*.ts",
    "../features/*/register-*.tsx",
    "../features/*/register-*.js",
    "../features/*/register-*.jsx",
    "../features/*/register-*.mjs",
    "!../features/integration/register-marketplace-props.tsx",
  ],
  { eager: true },
);

export const featureRegistry = resolveFeatureModules(discoveredModules);
