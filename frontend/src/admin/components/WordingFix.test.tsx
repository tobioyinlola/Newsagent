import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const post = vi.fn();
vi.mock("../api/client", () => ({ api: { POST: (...a: unknown[]) => post(...a) }, unwrap: async (p: Promise<{ data: unknown }>) => (await p).data }));
import { WordingFix } from "./WordingFix";

const found = { found: { story: 8, presenter_lines: 2 }, total: 10, kept: {}, applied: false, rerendering: false, version: null, note: "The founder's recorded answers are never changed." };
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) { this.setAttribute("open", ""); });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) { this.removeAttribute("open"); });
  post.mockReset();
});
afterEach(cleanup);
const open = (onDone = vi.fn()) => {
  render(<QueryClientProvider client={new QueryClient()}><WordingFix projectId="p1" onDone={onDone} /></QueryClientProvider>);
  fireEvent.click(screen.getByRole("button", { name: "Fix wording" }));
  fireEvent.change(screen.getByLabelText("Find"), { target: { value: "WIRE Africa" } });
  fireEvent.change(screen.getByLabelText("Replace with"), { target: { value: "Womenovate" } });
  return onDone;
};

it("checks first, changes nothing, then applies and can make the video again", async () => {
  const onDone = open();
  post.mockResolvedValueOnce({ data: found });
  fireEvent.click(screen.getByRole("button", { name: "Check" }));
  await screen.findByText(/Found in 10 places/);
  expect(post.mock.calls[0][1].body).toEqual({ find: "WIRE Africa", replace: "Womenovate", apply: false, rerender: false });
  expect(onDone).not.toHaveBeenCalled();
  expect(screen.getByText(/Written story/)).toBeTruthy();

  // making the video again asks first, in its own pop-up; going back changes nothing
  fireEvent.click(screen.getByRole("button", { name: "Change and make the video again" }));
  expect(await screen.findByText("Make this video again?")).toBeTruthy();
  expect(screen.getByText(/presenter-video credits/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Go back" }));
  expect(post).toHaveBeenCalledTimes(1);

  post.mockResolvedValueOnce({ data: { ...found, applied: true, rerendering: true, version: 2 } });
  fireEvent.click(screen.getByRole("button", { name: "Change and make the video again" }));
  fireEvent.click(screen.getByRole("button", { name: "Yes, make it again" }));
  await screen.findByText(/being made again/);
  expect(post.mock.calls[1][1].body).toEqual({ find: "WIRE Africa", replace: "Womenovate", apply: true, rerender: true });
  await waitFor(() => expect(onDone).toHaveBeenCalled());
});

it("says so when the wording is not found, and will not check an empty or unchanged change", async () => {
  open();
  post.mockResolvedValueOnce({ data: { ...found, found: {}, total: 0 } });
  fireEvent.click(screen.getByRole("button", { name: "Check" }));
  await screen.findByText(/not found, so there is nothing to change/);
  expect(screen.queryByRole("button", { name: /Change/ })).toBeNull();
  fireEvent.change(screen.getByLabelText("Replace with"), { target: { value: "WIRE Africa" } });
  expect((screen.getByRole("button", { name: "Check" }) as HTMLButtonElement).disabled).toBe(true);
});
