import { resolveFeatureModules } from "./featureRegistryCore";

const discoveredModules = import.meta.glob(
  ["../features/*/index.ts", "../features/*/index.tsx"],
  { eager: true },
);

export const featureRegistry = resolveFeatureModules(discoveredModules);
