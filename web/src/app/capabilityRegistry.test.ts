import { describe, expect, it } from "vitest";
import { RuntimeCapabilityRegistry } from "./capabilityRegistry";

describe("RuntimeCapabilityRegistry", () => {
  it("accepts the issue #9 registerCapability seam and resolves exact versions", () => {
    const registry = new RuntimeCapabilityRegistry();
    const catalog = { load: () => "catalog" };

    registry.registerFrom("platform", (target) => {
      target.registerCapability("platform.catalog", { contractVersion: 1, instance: catalog });
    });

    expect(registry.getCapability("platform.catalog", 1)).toBe(catalog);
    expect(registry.getCapability("platform.catalog", 2)).toBeUndefined();
    expect(registry.listCapabilities()).toEqual(["platform.catalog"]);
    expect(registry.diagnostics).toEqual([]);
  });

  it("fails closed when capability providers collide", () => {
    const registry = new RuntimeCapabilityRegistry();
    registry.registerFrom("first", (target) => {
      target.registerCapability("platform.documents", { contractVersion: 1, instance: { id: "first" } });
    });
    registry.registerFrom("second", (target) => {
      target.registerCapability("platform.documents", { contractVersion: 1, instance: { id: "second" } });
    });

    expect(registry.getCapability("platform.documents", 1)).toBeUndefined();
    expect(registry.listCapabilities()).toEqual([]);
    expect(registry.diagnostics).toContainEqual(expect.objectContaining({ code: "duplicate-capability" }));
  });

  it("rejects malformed registrations and registrar failures without throwing", () => {
    const registry = new RuntimeCapabilityRegistry();
    registry.registerFrom("malformed", (target) => {
      target.registerCapability("Bad Name", { contractVersion: 1, instance: {} });
    });
    registry.registerFrom("throwing", () => {
      throw new Error("registration failed");
    });

    expect(registry.listCapabilities()).toEqual([]);
    expect(registry.diagnostics.map((diagnostic) => diagnostic.code)).toEqual([
      "malformed-capability",
      "registrar-error",
    ]);
  });
});
