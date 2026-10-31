import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ReceiptUpload } from "./ReceiptUpload";

afterEach(cleanup);
it("rejects invalid, oversized and multiple files before requesting an upload", async () => {
  const onUpload = vi.fn();
  const { container } = render(<ReceiptUpload busy={false} filename="" onUpload={onUpload} onRemove={() => {}} />);
  const input = container.querySelector('input')!;
  fireEvent.change(input, { target: { files: [new File(["text"], "notes.txt", { type: "text/plain" })] } });
  expect(screen.getByRole("alert").textContent).toContain("PNG, JPEG or PDF");
  fireEvent.change(input, { target: { files: [new File([new Uint8Array(5 * 1024 * 1024 + 1)], "large.pdf", { type: "application/pdf" })] } });
  fireEvent.change(input, { target: { files: [new File(["pdf"], "one.pdf", { type: "application/pdf" }), new File(["pdf"], "two.pdf", { type: "application/pdf" })] } });
  expect(screen.getByRole("alert").textContent).toContain("one receipt");
  expect(onUpload).not.toHaveBeenCalled();
});
it("shows an in-flight state and allows retry after an unsuccessful upload", async () => {
  let finish!: (value: boolean) => void;
  const onUpload = vi.fn().mockImplementationOnce(() => new Promise<boolean>(resolve => { finish = resolve; })).mockResolvedValue(true);
  const { container } = render(<ReceiptUpload busy={false} filename="" onUpload={onUpload} onRemove={() => {}} />);
  const file = new File(["pdf"], "receipt.pdf", { type: "application/pdf" });
  const input = container.querySelector('input')!;
  fireEvent.change(input, { target: { files: [file] } });
  expect(screen.getByRole("status").textContent).toContain("Uploading and verifying");
  expect((screen.getByRole("button", { name: "Uploading…" }) as HTMLButtonElement).disabled).toBe(true);
  finish(false);
  await waitFor(() => expect(screen.getByRole("button", { name: "Choose receipt" })).toBeTruthy());
  fireEvent.change(input, { target: { files: [file] } });
  await waitFor(() => expect(onUpload).toHaveBeenCalledTimes(2));
});
it("supports replacement and removal without submitting the receipt", () => {
  const onRemove = vi.fn();
  render(<ReceiptUpload busy={false} filename="receipt.pdf" onUpload={vi.fn()} onRemove={onRemove} />);
  expect(screen.getByRole("status").textContent).toContain("ready to submit");
  expect(screen.getByRole("button", { name: "Replace receipt" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Remove" }));
  expect(onRemove).toHaveBeenCalledOnce();
});
