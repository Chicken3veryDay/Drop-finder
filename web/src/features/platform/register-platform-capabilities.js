import { CatalogGenerationClient } from '../../platform/catalog/catalog-generation-client.js';
import { MarketplaceQueryEngine } from '../../platform/workers/marketplace-query-engine.js';
import { VirtualMarketplaceAdapter } from '../../platform/virtualization/virtual-marketplace-adapter.js';
import { DocumentViewerCapability } from '../../platform/documents/document-viewer-capability.js';
import { PwaGenerationCoordinator } from '../../platform/pwa/pwa-generation-coordinator.js';
import { PLATFORM_CONTRACT_VERSION } from '../../platform/contracts.js';

/**
 * Versioned feature-registration seam matching issue #5 without importing its
 * implementation. Registries only need registerCapability(name, descriptor).
 */
export function registerPlatformCapabilities(registry, options = {}) {
  if (!registry || typeof registry.registerCapability !== 'function') {
    throw new TypeError('A capability registry with registerCapability() is required');
  }
  const capabilities = {
    catalog: new CatalogGenerationClient(options.catalog),
    query: new MarketplaceQueryEngine(options.query),
    virtualization: new VirtualMarketplaceAdapter(options.virtualization),
    documents: new DocumentViewerCapability(options.documents),
    pwa: new PwaGenerationCoordinator(options.pwa),
  };
  for (const [name, instance] of Object.entries(capabilities)) {
    registry.registerCapability(`platform.${name}`, {
      contractVersion: PLATFORM_CONTRACT_VERSION,
      instance,
    });
  }
  return capabilities;
}
