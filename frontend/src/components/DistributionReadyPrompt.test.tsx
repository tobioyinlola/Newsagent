import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import { DistributionReadyPrompt } from "./DistributionReadyPrompt";
function Location() { const location = useLocation(); return <p data-testid="path">{location.pathname}{location.search}</p>; }
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) { this.setAttribute("open", ""); });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) { this.removeAttribute("open"); });
});
afterEach(() => { cleanup(); localStorage.clear(); });
it("opens the correct project in distribution without initiating payment", () => {
  render(<MemoryRouter><DistributionReadyPrompt projectId="ready-123" workspaceId="workspace-one" /><Location /></MemoryRouter>);
  expect(screen.getByText(/2,500/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Yes, choose outlets" }));
  expect(screen.getByTestId("path").textContent).toBe("/distribution/request?project=ready-123");
  expect(screen.queryByRole("alertdialog")).toBeNull();
});
it("later dismisses persist for this project and workspace only", () => {
  const first = render(<MemoryRouter><DistributionReadyPrompt projectId="ready-123" workspaceId="one" /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "Maybe later" }));
  first.unmount();
  const again = render(<MemoryRouter><DistributionReadyPrompt projectId="ready-123" workspaceId="one" /></MemoryRouter>);
  expect(screen.queryByRole("alertdialog")).toBeNull();
  again.unmount();
  render(<MemoryRouter><DistributionReadyPrompt projectId="ready-123" workspaceId="two" /></MemoryRouter>);
  expect(screen.getByRole("alertdialog")).toBeTruthy();
});
