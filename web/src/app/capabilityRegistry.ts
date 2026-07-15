export type CapabilityContractVersion = number | string;

export interface CapabilityDescriptor<T = unknown> {
  contractVersion: CapabilityContractVersion;
  instance: T;
}

export interface CapabilityRegistrationTarget {
  registerCapability<T>(name: string, descriptor: CapabilityDescriptor<T>): boolean;
}

export interface CapabilityReader {
  getCapability<T = unknown>(name: string, expectedVersion?: CapabilityContractVersion): T | undefined;
  hasCapability(name: string, expectedVersion?: CapabilityContractVersion): boolean;
  listCapabilities(): readonly string[];
}

export interface CapabilityDiagnostic {
  source: string;
  code: "malformed-capability" | "duplicate-capability" | "registrar-error";
  message: string;
}

type UnknownRecord = Record<string, unknown>;
type CapabilityRegistrar = (registry: CapabilityRegistrationTarget) => unknown;

const CAPABILITY_NAME_PATTERN = /^[a-z0-9]+(?:[.-][a-z0-9]+)+$/;

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isVersion = (value: unknown): value is CapabilityContractVersion =>
  (Number.isInteger(value) && Number(value) > 0) || (typeof value === "string" && value.trim().length > 0);

const isThenable = (value: unknown): boolean =>
  isRecord(value) && typeof value.then === "function";

export class RuntimeCapabilityRegistry implements CapabilityRegistrationTarget, CapabilityReader {
  private readonly entries = new Map<string, CapabilityDescriptor>();
  private readonly conflictedNames = new Set<string>();
  private readonly recordedDiagnostics: CapabilityDiagnostic[] = [];
  private activeSource = "runtime";

  get diagnostics(): readonly CapabilityDiagnostic[] {
    return [...this.recordedDiagnostics];
  }

  registerCapability<T>(name: string, descriptor: CapabilityDescriptor<T>): boolean {
    if (!CAPABILITY_NAME_PATTERN.test(name)) {
      this.recordedDiagnostics.push({
        source: this.activeSource,
        code: "malformed-capability",
        message: `Capability name ${name || "<empty>"} must be a lowercase dotted or dashed identifier.`,
      });
      return false;
    }

    if (!isRecord(descriptor) || !isVersion(descriptor.contractVersion) || descriptor.instance === undefined || descriptor.instance === null) {
      this.recordedDiagnostics.push({
        source: this.activeSource,
        code: "malformed-capability",
        message: `Capability ${name} must provide a positive contractVersion and a non-null instance.`,
      });
      return false;
    }

    if (this.entries.has(name) || this.conflictedNames.has(name)) {
      this.entries.delete(name);
      this.conflictedNames.add(name);
      this.recordedDiagnostics.push({
        source: this.activeSource,
        code: "duplicate-capability",
        message: `Capability ${name} has multiple providers and was disabled.`,
      });
      return false;
    }

    this.entries.set(name, Object.freeze({
      contractVersion: descriptor.contractVersion,
      instance: descriptor.instance,
    }));
    return true;
  }

  registerFrom(source: string, registrar: CapabilityRegistrar): void {
    const previousSource = this.activeSource;
    this.activeSource = source;
    try {
      const result = registrar(this);
      if (isThenable(result)) {
        this.recordedDiagnostics.push({
          source,
          code: "registrar-error",
          message: "Capability registrars must complete synchronously during module discovery.",
        });
      }
    } catch (error) {
      this.recordedDiagnostics.push({
        source,
        code: "registrar-error",
        message: error instanceof Error ? error.message : "Capability registrar threw an unknown error.",
      });
    } finally {
      this.activeSource = previousSource;
    }
  }

  getCapability<T = unknown>(name: string, expectedVersion?: CapabilityContractVersion): T | undefined {
    if (this.conflictedNames.has(name)) return undefined;
    const descriptor = this.entries.get(name);
    if (!descriptor) return undefined;
    if (expectedVersion !== undefined && descriptor.contractVersion !== expectedVersion) return undefined;
    return descriptor.instance as T;
  }

  hasCapability(name: string, expectedVersion?: CapabilityContractVersion): boolean {
    return this.getCapability(name, expectedVersion) !== undefined;
  }

  listCapabilities(): readonly string[] {
    return [...this.entries.keys()].filter((name) => !this.conflictedNames.has(name)).sort();
  }
}
