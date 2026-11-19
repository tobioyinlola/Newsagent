import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { distributionApi } from "../../lib/distribution";
import { OutreachNeedsContact, splitEmails } from "./OutreachNeedsContact";

vi.mock("../../lib/distribution", async (orig) => ({ ...(await orig<typeof import("../../lib/distribution")>()), distributionApi: vi.fn() }));

const item = (id: string, name: string) => ({ placement_id: id, request_id: "r1", outlet_id: id, outlet_name: name, headline: "Acme opens in Lagos", requester: "owner@acme.test", paid_at: "2026-11-18T10:00:00Z", state: "needs_contact" });
const todo = { needs_contact: [item("p1", "Empire Magazine Africa"), item("p2", "Techpoint Africa")], waiting_mailbox: 0 };
const wrap = (ui: React.ReactElement) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);
const api = (over: Partial<typeof todo> = {}, put?: (b: unknown) => unknown) => vi.mocked(distributionApi).mockImplementation(async (path: string, _t: string | null, method = "GET", body?: unknown) => {
  if (method === "PUT") return (put ? put(body) : { state: "started" }) as never;
  return { ...todo, ...over } as never;
});
beforeEach(() => { vi.mocked(distributionApi).mockReset(); }); // braces: a returned function would be run by the test runner as clean-up
afterEach(cleanup);

describe("splitEmails", () => {
  it("takes one or several emails however they are separated, without repeats", () => {
    expect(splitEmails("Ada@Outlet.com")).toEqual(["ada@outlet.com"]);
    expect(splitEmails("a@x.com, b@x.com;c@x.com  d@x.com\ne@x.com, A@x.com")).toEqual(["a@x.com", "b@x.com", "c@x.com", "d@x.com", "e@x.com"]);
    expect(splitEmails("  ,; ")).toEqual([]);
  });
});

describe("outlets waiting for a contact", () => {
  it("lists each outlet with its request, and nothing when none are waiting", async () => {
    api();
    const { unmount } = wrap(<OutreachNeedsContact canManage onGoMailbox={() => undefined} />);
    expect(await screen.findByText("Waiting for a contact (2)")).toBeTruthy();
    expect(screen.getByText("Empire Magazine Africa")).toBeTruthy();
    expect(screen.getAllByText(/Acme opens in Lagos/).length).toBe(2);
    unmount();
    const before = vi.mocked(distributionApi).mock.calls.length;
    api({ needs_contact: [] });
    wrap(<OutreachNeedsContact canManage onGoMailbox={() => undefined} />);
    await waitFor(() => expect(vi.mocked(distributionApi).mock.calls.length).toBeGreaterThan(before)); // it asked, and got an empty list
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText(/Waiting for a contact/)).toBeNull();
  });

  it("saves one or several emails for an outlet, the first as the main contact, and says it started", async () => {
    let sent: unknown;
    api({}, (b) => { sent = b; return { state: "started" }; });
    wrap(<OutreachNeedsContact canManage onGoMailbox={() => undefined} />);
    await screen.findByText("Empire Magazine Africa");
    const emails = screen.getAllByLabelText("Email (one or several)")[0];
    expect((screen.getAllByRole("button", { name: "Save and email them" })[0] as HTMLButtonElement).disabled).toBe(true); // nothing typed yet
    fireEvent.change(screen.getAllByLabelText("Contact name (optional)")[0], { target: { value: "Ada" } });
    fireEvent.change(emails, { target: { value: "ada@empire.com, news@empire.com" } });
    expect(screen.getByText(/ada@empire.com is the main contact; the other 1 is copied/)).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Save and email them" })[0]);
    expect(await screen.findByText("Saved. We have started emailing Empire Magazine Africa.")).toBeTruthy();
    expect(sent).toEqual({ contact_name: "Ada", emails: ["ada@empire.com", "news@empire.com"] });
  });

  it("says it will go out when Gmail is connected, if there is no mailbox yet", async () => {
    api({}, () => ({ state: "waiting_mailbox" }));
    wrap(<OutreachNeedsContact canManage onGoMailbox={() => undefined} />);
    await screen.findByText("Empire Magazine Africa");
    fireEvent.change(screen.getAllByLabelText("Email (one or several)")[0], { target: { value: "ada@empire.com" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Save and email them" })[0]);
    expect(await screen.findByText(/as soon as Gmail is connected/)).toBeTruthy();
  });

  it("points to the mailbox when contacts are waiting only for Gmail", async () => {
    api({ needs_contact: [], waiting_mailbox: 3 });
    const go = vi.fn();
    wrap(<OutreachNeedsContact canManage onGoMailbox={go} />);
    expect(await screen.findByText(/3 outlets have a contact but are waiting for Gmail/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Connect Gmail" }));
    expect(go).toHaveBeenCalled();
  });

  it("shows the list but no forms to someone who cannot change things", async () => {
    api();
    wrap(<OutreachNeedsContact canManage={false} onGoMailbox={() => undefined} />);
    expect(await screen.findByText("Empire Magazine Africa")).toBeTruthy();
    expect(screen.queryByLabelText("Email (one or several)")).toBeNull();
  });

  it("shows an error when saving fails", async () => {
    vi.mocked(distributionApi).mockImplementation(async (_p: string, _t: string | null, method = "GET") => { if (method === "PUT") throw new Error("That outlet is not waiting for a contact."); return todo as never; });
    wrap(<OutreachNeedsContact canManage onGoMailbox={() => undefined} />);
    await screen.findByText("Empire Magazine Africa");
    fireEvent.change(screen.getAllByLabelText("Email (one or several)")[0], { target: { value: "ada@empire.com" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Save and email them" })[0]);
    expect(await screen.findByText(/not waiting for a contact/)).toBeTruthy();
  });
});
