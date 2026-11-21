import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Pager } from "./Pager";

afterEach(cleanup);

describe("Pager", () => {
  it("shows nothing when everything fits on one page", () => {
    const { container } = render(<Pager total={20} page={0} size={25} onPage={() => undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it("says which rows are showing and moves to the next and previous page", () => {
    const go = vi.fn();
    render(<Pager total={112} page={1} size={25} onPage={go} noun="customers" />);
    expect(screen.getByText("Showing 26 to 50 of 112 customers")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(go).toHaveBeenLastCalledWith(2);
    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(go).toHaveBeenLastCalledWith(0);
  });

  it("disables Previous on the first page and Next on the last", () => {
    const { rerender } = render(<Pager total={60} page={0} size={25} onPage={() => undefined} />);
    expect((screen.getByRole("button", { name: "Previous page" }) as HTMLButtonElement).disabled).toBe(true);
    rerender(<Pager total={60} page={2} size={25} onPage={() => undefined} />);
    expect((screen.getByRole("button", { name: "Next page" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("jumps to a numbered page and marks the current one", () => {
    const go = vi.fn();
    render(<Pager total={100} page={0} size={25} onPage={go} />);
    expect(screen.getByRole("button", { name: "Page 1" }).getAttribute("aria-current")).toBe("page");
    fireEvent.click(screen.getByRole("button", { name: "Page 3" }));
    expect(go).toHaveBeenCalledWith(2);
  });

  it("lets people choose how many rows to see, and goes back to the first page when they do", () => {
    const size = vi.fn(); const go = vi.fn();
    render(<Pager total={300} page={3} size={25} onPage={go} onSize={size} />);
    fireEvent.change(screen.getByLabelText("Rows per page"), { target: { value: "100" } });
    expect(size).toHaveBeenCalledWith(100);
    expect(go).toHaveBeenCalledWith(0);
  });

  it("is a labelled navigation region for screen readers", () => {
    render(<Pager total={100} page={0} size={25} onPage={() => undefined} />);
    expect(screen.getByRole("navigation", { name: "Pagination" })).toBeTruthy();
  });
});
