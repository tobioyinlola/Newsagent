import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import { BackButton, workspaceBackFallback } from "./BackButton";
function Location() { const location = useLocation(); return <p data-testid="location">{location.pathname}{location.search}</p>; }
afterEach(() => { cleanup(); window.history.replaceState(null, ""); });
it("returns a direct checkout link to billing instead of leaving the platform", () => {
  window.history.replaceState({ idx: 0 }, "");
  render(<MemoryRouter initialEntries={["/billing/transfer/example"]}><BackButton fallback="/settings/billing" /><Location /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "Go back" }));
  expect(screen.getByTestId("location").textContent).toBe("/settings/billing");
});
it("restores the previous in-app page with its query parameters", () => {
  window.history.replaceState({ idx: 1 }, "");
  render(<MemoryRouter initialEntries={["/distribution/request?draft=saved", "/settings/billing"]} initialIndex={1}><BackButton /><Location /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "Go back" }));
  expect(screen.getByTestId("location").textContent).toBe("/distribution/request?draft=saved");
});
it("chooses useful parent pages for direct links", () => {
  expect(workspaceBackFallback("/billing/transfer/id")).toBe("/settings/billing");
  expect(workspaceBackFallback("/ai-newsroom/project-id")).toBe("/ai-newsroom/videos");
  expect(workspaceBackFallback("/settings/password")).toBe("/settings/profile");
  expect(workspaceBackFallback("/brand")).toBe("/dashboard");
});
