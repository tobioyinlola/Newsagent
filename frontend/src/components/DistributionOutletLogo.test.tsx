import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { DistributionOutletLogo } from "./DistributionOutletLogo";

afterEach(cleanup);

it("a failed logo becomes readable initials without changing the outlet's selection label", () => {
  const { container } = render(<label><input type="checkbox" /><DistributionOutletLogo name="Empire Magazine Africa" /><span>Empire Magazine Africa</span></label>);
  const checkbox = screen.getByRole("checkbox", { name: "Empire Magazine Africa" });
  const image = container.querySelector("img")!;
  expect(image.getAttribute("src")).toContain("/distribution-logos/");
  fireEvent.error(image);
  expect(container.querySelector("img")).toBeNull();
  const initials = screen.getByText("EM");
  expect(initials.parentElement!.className).toContain("bg-white");
  fireEvent.click(checkbox);
  expect((checkbox as HTMLInputElement).checked).toBe(true);
});

it("an unverified publisher uses initials instead of an unrelated logo", () => {
  const { container } = render(<DistributionOutletLogo name="News Nine" />);
  expect(container.querySelector("img")).toBeNull();
  expect(screen.getByText("NN")).toBeTruthy();
});
