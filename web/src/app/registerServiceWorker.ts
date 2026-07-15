import { PUBLICATION_ASSETS } from "./assetPaths";

export const registerServiceWorker = (): void => {
  if (!("serviceWorker" in navigator) || import.meta.env.DEV) return;
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register(PUBLICATION_ASSETS.serviceWorker, { scope: "./" }).catch(() => {
      // Service-worker failure must not block the marketplace. Operational UI belongs to a later enhancer.
    });
  }, { once: true });
};
