import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useUrlState } from "../lib/urlState";
import { Check, Crumbs, EmptyState, PageIntro, Step, ToastProvider, useToast } from "./marketingUi";

afterEach(cleanup); // nothing from one test stays on the page for the next

describe("marketing building blocks", () => {
  it("shows where you are, and only earlier steps are links", () => {
    render(<MemoryRouter><Crumbs trail={[["Campaigns", "/marketing/campaigns"], ["Morning send"]]} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Campaigns" }).getAttribute("href")).toBe("/marketing/campaigns");
    expect(screen.getByText("Morning send").getAttribute("aria-current")).toBe("page");
    expect(screen.queryByRole("link", { name: "Morning send" })).toBeNull();
  });

  it("explains a screen in one sentence and keeps the longer help tucked away", () => {
    render(<PageIntro title="Segments" how={["Add rules.", "Check the people."]}>A saved group of people.</PageIntro>);
    expect(screen.getByRole("heading", { name: "Segments" })).toBeTruthy();
    expect(screen.getByText("A saved group of people.")).toBeTruthy();
    expect(screen.getByText("How does this work?").closest("details")?.hasAttribute("open")).toBe(false);
    expect(screen.getByText("Check the people.")).toBeTruthy();
  });

  it("says whether a checklist line is done or still to do, for people who can't see the tick", () => {
    render(<ul><Check done>Segment made</Check><Check done={false} action={<button>Do it</button>}>Write an email</Check></ul>);
    expect(screen.getByText("Done:")).toBeTruthy();
    expect(screen.getByText("To do:")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Do it" })).toHaveLength(1); // the action only shows while it's still to do
  });

  it("tells you what to do next from an empty list", () => {
    render(<EmptyState title="You haven’t made a segment yet" actions={<button>Make one</button>}>Start from an example.</EmptyState>);
    expect(screen.getByText("Start from an example.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Make one" })).toBeTruthy();
  });

  it("numbers the parts of a form", () => {
    render(<Step n={2} title="Write it" hint="What people read."><input aria-label="Subject" /></Step>);
    expect(screen.getByRole("heading", { name: "Write it" })).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByLabelText("Subject")).toBeTruthy();
  });
});

describe("saved messages", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());
  function Button() { const toast = useToast(); return <button onClick={() => toast("Segment saved.")}>save</button>; }

  it("appears after an action and goes away by itself", () => {
    render(<ToastProvider><Button /></ToastProvider>);
    fireEvent.click(screen.getByText("save"));
    expect(screen.getByText("Segment saved.")).toBeTruthy();
    act(() => { vi.advanceTimersByTime(4500); });
    expect(screen.queryByText("Segment saved.")).toBeNull();
  });
});

describe("where you are lives in the address", () => {
  function Probe() {
    const url = useUrlState();
    const loc = useLocation();
    return <div><span data-testid="at">{loc.pathname + loc.search}</span><button onClick={() => url.set({ edit: "new", example: "2" })}>open</button><button onClick={() => url.set({ edit: null, example: null })}>close</button><span data-testid="edit">{url.get("edit") ?? "none"}</span></div>;
  }
  const mount = (start: string) => render(<MemoryRouter initialEntries={[start]}><Routes><Route path="/marketing/*" element={<Probe />} /></Routes></MemoryRouter>);

  it("opens and closes an editor through the address, keeping the rest of it", () => {
    mount("/marketing/segments?tab=x");
    expect(screen.getByTestId("edit").textContent).toBe("none");
    fireEvent.click(screen.getByText("open"));
    expect(screen.getByTestId("at").textContent).toBe("/marketing/segments?tab=x&edit=new&example=2");
    expect(screen.getByTestId("edit").textContent).toBe("new");
    fireEvent.click(screen.getByText("close"));
    expect(screen.getByTestId("at").textContent).toBe("/marketing/segments?tab=x");
  });

  it("picks up an editor that was open in a shared or refreshed link", () => {
    mount("/marketing/segments?edit=abc123");
    expect(screen.getByTestId("edit").textContent).toBe("abc123");
  });
});
