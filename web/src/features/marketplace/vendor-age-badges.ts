import "./vendor-age-badges.css";

export type VendorAgeDisplay = "verification" | "confirmation" | "no_gate_observed" | "unknown";

export interface VendorAgeProfile {
  vendor_id: string;
  vendor_name: string;
  classification: string;
  display: VendorAgeDisplay;
  provider?: string;
  scope?: string;
  summary?: string;
  evidence_url?: string;
}

interface VendorAgeIndex {
  schema_version: string;
  vendors: VendorAgeProfile[];
}

const DEFAULT_INDEX_URL = "./data/catalog-v4/vendor-age-verification.json";

export function normalizeVendorName(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function ageCheckLabel(display: VendorAgeDisplay): string {
  switch (display) {
    case "verification":
      return "Verification";
    case "confirmation":
      return "Confirmation";
    case "no_gate_observed":
      return "No gate observed";
    default:
      return "Unknown";
  }
}

export function displayForClassification(classification: string): VendorAgeDisplay {
  if (classification === "identity_verification_required" || classification === "identity_verification_conditional") {
    return "verification";
  }
  if (classification === "self_attestation_21_plus") return "confirmation";
  if (classification === "no_observed_gate") return "no_gate_observed";
  return "unknown";
}

function safeProfile(raw: unknown): VendorAgeProfile | null {
  if (!raw || typeof raw !== "object") return null;
  const value = raw as Partial<VendorAgeProfile>;
  if (typeof value.vendor_id !== "string" || typeof value.vendor_name !== "string") return null;
  const classification = typeof value.classification === "string" ? value.classification : "uncertain";
  const requestedDisplay = value.display;
  const display: VendorAgeDisplay = ["verification", "confirmation", "no_gate_observed", "unknown"].includes(
    String(requestedDisplay),
  )
    ? requestedDisplay as VendorAgeDisplay
    : displayForClassification(classification);
  return {
    vendor_id: value.vendor_id,
    vendor_name: value.vendor_name,
    classification,
    display,
    provider: typeof value.provider === "string" ? value.provider : "none_observed",
    scope: typeof value.scope === "string" ? value.scope : "unknown",
    summary: typeof value.summary === "string" ? value.summary : "Age-control details have not been confirmed.",
    evidence_url: typeof value.evidence_url === "string" ? value.evidence_url : "",
  };
}

export function profileMap(payload: unknown): Map<string, VendorAgeProfile> {
  if (!payload || typeof payload !== "object") return new Map();
  const index = payload as Partial<VendorAgeIndex>;
  if (!Array.isArray(index.vendors)) return new Map();
  const profiles = new Map<string, VendorAgeProfile>();
  for (const raw of index.vendors) {
    const profile = safeProfile(raw);
    if (profile) profiles.set(normalizeVendorName(profile.vendor_name), profile);
  }
  return profiles;
}

function badgeTitle(profile: VendorAgeProfile): string {
  const parts = [profile.summary];
  if (profile.provider && profile.provider !== "none_observed") parts.push(`Provider: ${profile.provider}`);
  if (profile.scope && profile.scope !== "unknown") parts.push(`Scope: ${profile.scope}`);
  return parts.filter(Boolean).join(" ");
}

export function applyVendorAgeBadges(root: ParentNode, profiles: ReadonlyMap<string, VendorAgeProfile>): void {
  for (const product of root.querySelectorAll<HTMLElement>(".df-product")) {
    const expanded = product.querySelector<HTMLElement>(".df-expanded");
    if (!expanded) continue;
    const facts = expanded.querySelector<HTMLElement>(".df-expanded-facts");
    const vendor = product.querySelector<HTMLElement>(".df-vendor-identity");
    if (!facts || !vendor) continue;

    const key = normalizeVendorName(vendor.textContent ?? "");
    const profile = profiles.get(key);
    const current = facts.querySelector<HTMLElement>("[data-vendor-age-check]");
    if (!profile) {
      current?.remove();
      continue;
    }

    const valueText = ageCheckLabel(profile.display);
    const title = badgeTitle(profile);
    const ariaLabel = `Age check: ${valueText}. ${profile.summary ?? ""}`.trim();
    const currentValue = current?.querySelector<HTMLElement>("strong");
    if (
      current
      && current.dataset.vendorAgeCheck === profile.display
      && current.className === "df-age-check-fact"
      && current.title === title
      && current.getAttribute("aria-label") === ariaLabel
      && currentValue?.className === `df-age-check-badge df-age-check-${profile.display}`
      && currentValue.textContent === valueText
    ) {
      continue;
    }

    const row = current ?? globalThis.document.createElement("p");
    row.dataset.vendorAgeCheck = profile.display;
    row.className = "df-age-check-fact";
    row.title = title;
    row.setAttribute("aria-label", ariaLabel);
    row.replaceChildren();

    const label = globalThis.document.createElement("span");
    label.textContent = "Age check";
    const value = globalThis.document.createElement("strong");
    value.className = `df-age-check-badge df-age-check-${profile.display}`;
    value.textContent = valueText;
    row.append(label, value);
    if (!current) facts.append(row);
  }
}

export function installVendorAgeBadges(options: {
  root?: ParentNode;
  indexUrl?: string;
  fetchImpl?: typeof fetch;
} = {}): () => void {
  const root = options.root ?? globalThis.document;
  const fetchImpl = options.fetchImpl ?? globalThis.fetch?.bind(globalThis);
  const controller = new AbortController();
  let observer: MutationObserver | null = null;

  if (!fetchImpl) return () => controller.abort();

  void fetchImpl(options.indexUrl ?? DEFAULT_INDEX_URL, {
    signal: controller.signal,
    cache: "no-store",
    credentials: "same-origin",
  }).then(async (response) => {
    if (!response.ok) throw new Error(`Vendor age index request failed with ${response.status}`);
    const profiles = profileMap(await response.json());
    if (controller.signal.aborted || profiles.size === 0) return;
    const apply = () => applyVendorAgeBadges(root, profiles);
    apply();
    observer = new MutationObserver(apply);
    observer.observe(root, { childList: true, subtree: true });
  }).catch((error: unknown) => {
    if (!(error instanceof DOMException && error.name === "AbortError")) {
      // The catalog can legitimately predate this optional metadata asset.
      // Product browsing remains fully functional when the badge is unavailable.
    }
  });

  return () => {
    controller.abort();
    observer?.disconnect();
  };
}
