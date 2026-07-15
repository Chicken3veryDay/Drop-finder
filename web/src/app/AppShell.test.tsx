import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import baseCss from "../styles/base.css?raw";
import { FEATURE_API_VERSION } from "./featureContract";
import { resolveFeatureModules } from "./featureRegistryCore";
import { AppShell } from "./AppShell";

const registry = resolveFeatureModules({
  marketplace: {
    default: {
      apiVersion: FEATURE_API_VERSION,
      id: "marketplace.test",
      kind: "marketplace",
      order: 10,
      capabilities: ["marketplace.surface"],
      slots: { marketplaceSurface: () => <div>Test results</div> },
    },
  },
});

describe("AppShell", () => {
  it("exposes concise marketplace landmarks and accessible names", () => {
    render(<AppShell registry={registry} />);
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAccessibleName("Dropfinder Marketplace");
    expect(screen.getByRole("searchbox", { name: "Search strains and vendors" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Marketplace filters" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Marketplace results" })).toBeInTheDocument();
    expect(screen.queryByText(/settings|favorites|recommended|source health/i)).not.toBeInTheDocument();
  });

  it("focuses search with slash and clears then leaves it with Escape", async () => {
    const user = userEvent.setup();
    render(<AppShell registry={registry} />);
    const search = screen.getByRole("searchbox", { name: "Search strains and vendors" });

    await user.keyboard("/");
    expect(search).toHaveFocus();
    await user.type(search, "blue dream");
    await user.keyboard("{Escape}");
    expect(search).toHaveValue("");
    expect(search).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(search).not.toHaveFocus();
  });

  it("provides a focus-visible rule rather than removing keyboard focus", () => {
    expect(baseCss).toContain(".focus-ring:focus-visible");
    expect(baseCss).toContain("--focus-ring");
  });
});
