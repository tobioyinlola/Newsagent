import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { distributionApi } from "../../lib/distribution";
import { OutreachMailbox, type MailboxStatus } from "./OutreachMailbox";

vi.mock("../../lib/distribution", async (orig) => ({ ...(await orig<typeof import("../../lib/distribution")>()), distributionApi: vi.fn() }));

const none: MailboxStatus = { connected: false, address: null, source: null, mode: null, sends_via: null, connected_by: null, connected_at: null, last_polled_at: null, last_error: "", ready: false, outreach_on: true };
const connected: MailboxStatus = { ...none, connected: true, address: "outreach.cf@gmail.com", source: "back office", mode: "smtp", sends_via: "Gmail", connected_by: "ops@example.com", connected_at: "2026-11-19T08:00:00Z", last_polled_at: "2026-11-19T09:00:00Z", ready: true };
const wrap = (ui: React.ReactElement) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);
const fill = () => { fireEvent.change(screen.getByLabelText("Gmail address"), { target: { value: "name@gmail.com" } }); fireEvent.change(screen.getByLabelText("App password"), { target: { value: "abcd efgh ijkl mnop" } }); };
const calls = () => vi.mocked(distributionApi).mock.calls;
beforeEach(() => { vi.mocked(distributionApi).mockReset(); }); // braces: a returned function would be run by the test runner as clean-up
afterEach(cleanup);

describe("connecting a Gmail", () => {
  it("walks through the Google steps with links, and asks for the address and app password", () => {
    wrap(<OutreachMailbox status={none} canManage onChanged={() => undefined} />);
    expect(screen.getByRole("heading", { name: "Connect your Gmail" })).toBeTruthy();
    const links = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(links).toContain("https://myaccount.google.com/apppasswords");
    expect(links.some((h) => h?.includes("two-step-verification"))).toBe(true);
    expect(links.some((h) => h?.includes("fwdandpop"))).toBe(true);
    expect((screen.getByLabelText("App password") as HTMLInputElement).type).toBe("password"); // never shown on screen
    expect((screen.getByRole("button", { name: "Connect Gmail" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("checks the connection without saving and says what would happen", async () => {
    vi.mocked(distributionApi).mockResolvedValue({ ok: true, mode: "relay", message: "Connected for reading replies. Our hosting blocks sending straight through Gmail…", steps: [] } as never);
    wrap(<OutreachMailbox status={none} canManage onChanged={() => undefined} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Check connection" }));
    expect(await screen.findByText(/hosting blocks sending/)).toBeTruthy();
    expect(calls()[0].slice(0, 4)).toEqual(["admin/outreach/mailbox/test", null, "POST", { address: "name@gmail.com", app_password: "abcd efgh ijkl mnop" }]);
  });

  it("connects, forgets the password in the form, and tells the page to refresh", async () => {
    vi.mocked(distributionApi).mockResolvedValue({} as never);
    const onChanged = vi.fn();
    wrap(<OutreachMailbox status={none} canManage onChanged={onChanged} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Connect Gmail" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect((screen.getByLabelText("App password") as HTMLInputElement).value).toBe("");
    expect(screen.getByText(/Emails that were waiting for a mailbox are now on their way/)).toBeTruthy();
    expect(calls()[0][2]).toBe("PUT");
  });

  it("shows why it failed, with the steps to fix it", async () => {
    vi.mocked(distributionApi).mockImplementation(async () => { throw new ApiError(422, "x", { message: "Google did not accept that address and app password.", steps: ["Turn on 2-step verification.", "Create an app password."] }); });
    wrap(<OutreachMailbox status={none} canManage onChanged={() => undefined} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Connect Gmail" }));
    expect(await screen.findByText(/did not accept that address/)).toBeTruthy();
    expect(screen.getByText("Create an app password.")).toBeTruthy();
  });

  it("is not changeable without permission", () => {
    wrap(<OutreachMailbox status={none} canManage={false} onChanged={() => undefined} />);
    expect((screen.getByLabelText("Gmail address") as HTMLInputElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Connect Gmail" })).toBeNull();
    expect(screen.getByText(/can see this page but not change/)).toBeTruthy();
  });

  it("says when outreach itself is switched off on the server", () => {
    wrap(<OutreachMailbox status={{ ...none, outreach_on: false }} canManage onChanged={() => undefined} />);
    expect(screen.getByText(/switched off on the server/)).toBeTruthy();
  });
});

describe("once connected", () => {
  it("shows the address and how it sends, but never a password", () => {
    wrap(<OutreachMailbox status={connected} canManage onChanged={() => undefined} />);
    expect(screen.getByText("outreach.cf@gmail.com")).toBeTruthy();
    expect(screen.getByText("Gmail")).toBeTruthy();
    expect(screen.getByText(/ops@example.com/)).toBeTruthy();
    expect(screen.queryByLabelText("App password")).toBeNull(); // the form is hidden until you ask to change it
    expect(document.body.textContent).not.toMatch(/abcd/);
  });

  it("explains the relay way of sending when the host blocks Gmail", () => {
    wrap(<OutreachMailbox status={{ ...connected, mode: "relay", sends_via: "our email service, with a copy to your Gmail" }} canManage onChanged={() => undefined} />);
    expect(screen.getByText(/does not allow sending straight through Gmail/)).toBeTruthy();
  });

  it("raises an alert when Google stopped accepting the password", () => {
    wrap(<OutreachMailbox status={{ ...connected, last_error: "We could not read the inbox. The app password may have been removed: connect again." }} canManage onChanged={() => undefined} />);
    expect(screen.getByRole("alert").textContent).toContain("connect again");
  });

  it("lets you switch to a different Gmail", () => {
    wrap(<OutreachMailbox status={connected} canManage onChanged={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Use a different Gmail or password" }));
    expect(screen.getByLabelText("App password")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Keep this Gmail" }));
    expect(screen.queryByLabelText("App password")).toBeNull();
  });

  it("asks twice before disconnecting", async () => {
    vi.mocked(distributionApi).mockResolvedValue({} as never);
    const onChanged = vi.fn();
    wrap(<OutreachMailbox status={connected} canManage onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(calls().length).toBe(0); // the first press only asks
    fireEvent.click(screen.getByRole("button", { name: "Yes, disconnect" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(calls()[0].slice(0, 3)).toEqual(["admin/outreach/mailbox", null, "DELETE"]);
  });

  it("offers a test email once there is somewhere to send from", () => {
    wrap(<OutreachMailbox status={connected} canManage onChanged={() => undefined} />);
    expect(screen.getByLabelText("Send a test email to yourself")).toBeTruthy();
  });
});
