import { beforeEach, describe, expect, it } from "vitest";
import {
  ageCheckLabel,
  applyVendorAgeBadges,
  displayForClassification,
  normalizeVendorName,
  profileMap,
} from "./vendor-age-badges";

describe("vendor age badges", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("keeps identity verification distinct from self-attestation", () => {
    expect(displayForClassification("identity_verification_required")).toBe("verification");
    expect(displayForClassification("identity_verification_conditional")).toBe("verification");
    expect(displayForClassification("self_attestation_21_plus")).toBe("confirmation");
    expect(ageCheckLabel("confirmation")).toBe("Confirmation");
  });

  it("normalizes vendor punctuation for published profile lookup", () => {
    expect(normalizeVendorName("Sherlocks Glass & Dispensary")).toBe("sherlocks glass and dispensary");
  });

  it("injects a compact fact only into an expanded matching row without rewriting it", async () => {
    document.body.innerHTML = `
      <article class="df-product">
        <div class="df-row"><span class="df-vendor-identity">Flow Gardens</span></div>
        <div class="df-expanded"><div class="df-expanded-facts"></div></div>
      </article>
      <article class="df-product">
        <div class="df-row"><span class="df-vendor-identity">Unknown Shop</span></div>
        <div class="df-expanded"><div class="df-expanded-facts"></div></div>
      </article>
    `;
    const profiles = profileMap({
      schema_version: "dropfinder-vendor-age-index-v1",
      vendors: [{
        vendor_id: "flow_gardens",
        vendor_name: "Flow Gardens",
        classification: "self_attestation_21_plus",
        display: "confirmation",
        summary: "Visitor confirms they are 21 or older.",
      }],
    });

    applyVendorAgeBadges(document, profiles);
    const badge = document.querySelector<HTMLElement>("[data-vendor-age-check]");
    expect(badge).not.toBeNull();

    let mutations = 0;
    const observer = new MutationObserver((records) => {
      mutations += records.length;
    });
    observer.observe(badge as HTMLElement, { childList: true, subtree: true, attributes: true });
    applyVendorAgeBadges(document, profiles);
    await Promise.resolve();
    observer.disconnect();

    const badges = document.querySelectorAll("[data-vendor-age-check]");
    expect(badges).toHaveLength(1);
    expect(badges[0]).toHaveTextContent("Age checkConfirmation");
    expect(badges[0]).toHaveAttribute("data-vendor-age-check", "confirmation");
    expect(mutations).toBe(0);
  });
});
