import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import { Field, ModalPortalHost } from "../design";
import type { ResolvedFeatureRegistry } from "./featureContract";

interface AppShellProps {
  registry: ResolvedFeatureRegistry;
}

const isEditableTarget = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
};

export const AppShell = ({ registry }: AppShellProps): ReactNode => {
  const [searchValue, setSearchValue] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const [portalElement, setPortalElement] = useState<HTMLDivElement | null>(null);
  const { search: SearchSlot, filters: FiltersSlot, resultHeader: ResultHeaderSlot, marketplaceSurface: MarketplaceSlot, overlay: OverlaySlot } = registry.slots;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "/" && !event.metaKey && !event.ctrlKey && !event.altKey && !isEditableTarget(event.target)) {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === "Escape" && document.activeElement === searchRef.current) {
        if (searchValue) setSearchValue("");
        else searchRef.current?.blur();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [searchValue]);

  const handleSearchKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>): void => {
    if (event.key !== "Escape") return;
    event.stopPropagation();
    if (searchValue) setSearchValue("");
    else event.currentTarget.blur();
  };

  const developmentError = import.meta.env.DEV && !registry.primaryMarketplace
    ? "Marketplace module unavailable."
    : null;

  return (
    <div className="app-shell">
      <header className="app-header">
        <a className="wordmark focus-ring" href="./" aria-label="dropfinder home">dropfinder</a>
        <span className="app-section" aria-current="page">Marketplace</span>
      </header>

      <main className="marketplace" aria-labelledby="marketplace-title">
        <h1 id="marketplace-title" className="visually-hidden">Dropfinder Marketplace</h1>

        <section className="search-region" aria-label="Marketplace search">
          {SearchSlot ? (
            <SearchSlot value={searchValue} onValueChange={setSearchValue} inputRef={searchRef} />
          ) : (
            <Field
              ref={searchRef}
              label="Search strains and vendors"
              type="search"
              name="marketplace-search"
              autoComplete="off"
              placeholder="Search strains or vendors"
              value={searchValue}
              onChange={(event) => setSearchValue(event.currentTarget.value)}
              onKeyDown={handleSearchKeyDown}
            />
          )}
        </section>

        <section id="filter-bar-slot" className="filter-region" aria-label="Marketplace filters">
          {FiltersSlot ? <FiltersSlot searchValue={searchValue} /> : null}
        </section>

        <section id="result-header-slot" className="result-header-region" aria-label="Marketplace result summary" aria-live="polite">
          {ResultHeaderSlot ? <ResultHeaderSlot searchValue={searchValue} /> : null}
        </section>

        <section id="marketplace-surface-slot" className="result-region" aria-label="Marketplace results">
          {MarketplaceSlot ? <MarketplaceSlot searchValue={searchValue} /> : null}
          {developmentError ? <p className="inline-error" role="alert">{developmentError}</p> : null}
        </section>
      </main>

      <ModalPortalHost ref={setPortalElement} />
      {OverlaySlot ? <OverlaySlot portalElement={portalElement} /> : null}
    </div>
  );
};
