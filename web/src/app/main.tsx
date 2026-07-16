import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppShell } from "./AppShell";
import { featureRegistry } from "./featureRegistry";
import { registerServiceWorker } from "./registerServiceWorker";
import { installVendorAgeBadges } from "../features/marketplace/vendor-age-badges";
import "../styles/index.css";
import "../features/marketplace/marketplace-mobile-parity.css";

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root application mount.");

createRoot(root).render(
  <StrictMode>
    <AppShell registry={featureRegistry} />
  </StrictMode>,
);

installVendorAgeBadges();
registerServiceWorker();
