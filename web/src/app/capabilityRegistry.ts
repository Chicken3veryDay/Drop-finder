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
  value !== null
  && (typeof value === "object" || typeof value === "function")
  && typeof (value as { then?: unknown }).then === "function";

const normalizeCapability = <T>(
  source: string,
  name: string,
  descriptor: CapabilityDescriptor<T>,
): { descriptor: CapabilityDescriptor } | { diagnostic: CapabilityDiagnostic } => {
  if (!CAPABILITY_NAME_PATTERN.test(name)) {
    return {
      diagnostic: {
        source,
        code: "malformed-capability",
        message: `Capability name ${name || "<empty>"} must be a lowercase dotted or dashed identifier.`,
      },
    };
  }

  if (!isRecord(descriptor) || !isVersion(descriptor.contractVersion) || descriptor.instance === undefined || descriptor.instance === null) {
    return {
      diagnostic: {
        source,
        code: "malformed-capability",
        message: `Capability ${name} must provide a positive contractVersion and a non-null instance.`,
      },
    };
  }

  return {
    descriptor: Object.freeze({
      contractVersion: descriptor.contractVersion,
      instance: descriptor.instance,
    }),
  };
};

export class RuntimeCapabilityRegistry implements CapabilityRegistrationTarget, CapabilityReader {
  private readonly entries = new Map<string, CapabilityDescriptor>();
  private readonly conflictedNames = new Set<string>();
  private readonly recordedDiagnostics: CapabilityDiagnostic[] = [];

  get diagnostics(): readonly CapabilityDiagnostic[] {
    return [...this.recordedDiagnostics];
  }

  registerCapability<T>(name: string, descriptor: CapabilityDescriptor<T>): boolean {
    const normalized = normalizeCapability("runtime", name, descriptor);
    if ("diagnostic" in normalized) {
      this.recordedDiagnostics.push(normalized.diagnostic);
      return false;
    }

    if (this.entries.has(name) || this.conflictedNames.has(name)) {
      this.entries.delete(name);
      this.conflictedNames.add(name);
      this.recordedDiagnostics.push({
        source: "runtime",
        code: "duplicate-capability",
        message: `Capability ${name} has multiple providers and was disabled.`,
      });
      return false;
    }

    this.entries.set(name, normalized.descriptor);
    return true;
  }

  registerFrom(source: string, registrar: CapabilityRegistrar): void {
    const stagedEntries = new Map<string, CapabilityDescriptor>();
    const stagedDiagnostics: CapabilityDiagnostic[] = [];
    let closed = false;

    const target: CapabilityRegistrationTarget = Object.freeze({
      registerCapability: <T>(name: string, descriptor: CapabilityDescriptor<T>): boolean => {
        if (closed) return false;
        const normalized = normalizeCapability(source, name, descriptor);
        if ("diagnostic" in normalized) {
          stagedDiagnostics.push(normalized.diagnostic);
          return false;
        }
        if (stagedEntries.has(name)) {
          stagedDiagnostics.push({
            source,
            code: "duplicate-capability",
            message: `Capability ${name} has multiple providers and was disabled.`,
          });
          return false;
        }
        stagedEntries.set(name, normalized.descriptor);
        return true;
      },
    });

    try {
      const result = registrar(target);
      closed = true;
      if (isThenable(result)) {
        void Promise.resolve(result).catch(() => undefined);
        this.recordedDiagnostics.push({
          source,
          code: "registrar-error",
          message: "Capability registrars must complete synchronously during module discovery.",
        });
        return;
      }
    } catch (error) {
      closed = true;
      this.recordedDiagnostics.push({
        source,
        code: "registrar-error",
        message: error instanceof Error ? error.message : "Capability registrar threw an unknown error.",
      });
      return;
    }

    if (stagedDiagnostics.length > 0) {
      this.recordedDiagnostics.push(...stagedDiagnostics);
      return;
    }

    const collisions = [...stagedEntries.keys()].filter((name) => this.entries.has(name) || this.conflictedNames.has(name));
    if (collisions.length > 0) {
      for (const name of collisions) {
        this.entries.delete(name);
        this.conflictedNames.add(name);
        this.recordedDiagnostics.push({
          source,
          code: "duplicate-capability",
          message: `Capability ${name} has multiple providers and was disabled.`,
        });
      }
      return;
    }

    for (const [name, descriptor] of stagedEntries) this.entries.set(name, descriptor);
  }

  toReader(): CapabilityReader {
    const entries = new Map(this.entries);
    const conflictedNames = new Set(this.conflictedNames);
    return Object.freeze({
      getCapability: <T = unknown>(name: string, expectedVersion?: CapabilityContractVersion): T | undefined => {
        if (conflictedNames.has(name)) return undefined;
        const descriptor = entries.get(name);
        if (!descriptor) return undefined;
        if (expectedVersion !== undefined && descriptor.contractVersion !== expectedVersion) return undefined;
        return descriptor.instance as T;
      },
      hasCapability: (name: string, expectedVersion?: CapabilityContractVersion): boolean => {
        if (conflictedNames.has(name)) return false;
        const descriptor = entries.get(name);
        if (!descriptor) return false;
        return expectedVersion === undefined || descriptor.contractVersion === expectedVersion;
      },
      listCapabilities: (): readonly string[] =>
        [...entries.keys()].filter((name) => !conflictedNames.has(name)).sort(),
    });
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
