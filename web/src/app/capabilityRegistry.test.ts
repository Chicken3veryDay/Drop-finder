import { describe, expect, it } from "vitest";
import { RuntimeCapabilityRegistry, type CapabilityRegistrationTarget } from "./capabilityRegistry";

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
    expect(registry.diagnostics).toContainEqual(expect.objectContaining({ source: "second", code: "duplicate-capability" }));
  });

  it("rejects malformed registrations atomically and records registrar failures without throwing", () => {
    const registry = new RuntimeCapabilityRegistry();
    registry.registerFrom("malformed", (target) => {
      target.registerCapability("platform.catalog", { contractVersion: 1, instance: {} });
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

  it("discards every staged write when a registrar throws and preserves earlier providers", () => {
    const registry = new RuntimeCapabilityRegistry();
    const original = { id: "original" };
    registry.registerFrom("first", (target) => {
      target.registerCapability("platform.documents", { contractVersion: 1, instance: original });
    });

    registry.registerFrom("throwing", (target) => {
      target.registerCapability("platform.catalog", { contractVersion: 1, instance: { id: "partial" } });
      target.registerCapability("platform.documents", { contractVersion: 1, instance: { id: "duplicate" } });
      throw new Error("boom");
    });

    expect(registry.getCapability("platform.documents", 1)).toBe(original);
    expect(registry.getCapability("platform.catalog", 1)).toBeUndefined();
    expect(registry.diagnostics).toEqual([
      { source: "throwing", code: "registrar-error", message: "boom" },
    ]);
  });

  it("rejects thenables and permanently closes retained registration targets", async () => {
    const registry = new RuntimeCapabilityRegistry();
    let retained: CapabilityRegistrationTarget | undefined;
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });

    registry.registerFrom("async", async (target) => {
      retained = target;
      await gate;
      target.registerCapability("platform.query", { contractVersion: 1, instance: { id: "late" } });
    });

    expect(registry.listCapabilities()).toEqual([]);
    expect(registry.diagnostics).toEqual([
      {
        source: "async",
        code: "registrar-error",
        message: "Capability registrars must complete synchronously during module discovery.",
      },
    ]);

    release();
    await gate;
    await Promise.resolve();
    expect(registry.listCapabilities()).toEqual([]);
    expect(retained?.registerCapability("platform.catalog", { contractVersion: 1, instance: {} })).toBe(false);
    expect(registry.listCapabilities()).toEqual([]);
  });

  it("commits successful registrars atomically and exposes an immutable reader snapshot", () => {
    const registry = new RuntimeCapabilityRegistry();
    let retained: CapabilityRegistrationTarget | undefined;
    const catalog = { id: "catalog" };
    const query = { id: "query" };

    registry.registerFrom("platform", (target) => {
      retained = target;
      target.registerCapability("platform.catalog", { contractVersion: 1, instance: catalog });
      target.registerCapability("platform.query", { contractVersion: 2, instance: query });
    });

    const reader = registry.toReader();
    expect(Object.isFrozen(reader)).toBe(true);
    expect("registerCapability" in reader).toBe(false);
    expect(reader.getCapability("platform.catalog", 1)).toBe(catalog);
    expect(reader.getCapability("platform.query", 2)).toBe(query);
    expect(reader.listCapabilities()).toEqual(["platform.catalog", "platform.query"]);

    expect(retained?.registerCapability("platform.documents", { contractVersion: 1, instance: {} })).toBe(false);
    registry.registerCapability("platform.documents", { contractVersion: 1, instance: {} });
    expect(reader.listCapabilities()).toEqual(["platform.catalog", "platform.query"]);
  });
});
