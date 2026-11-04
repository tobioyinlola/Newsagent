import { expect, test } from "@playwright/test";

const LINKS: [string, string][] = [
  ["Instagram", "https://www.instagram.com/coverfounder"],
  ["X", "https://x.com/Coverfounder"],
  ["LinkedIn", "https://www.linkedin.com/company/cover-founder/"],
];

test("the footer shows Cover Founder's Instagram, X and LinkedIn icons, each opening its page in a new tab", async ({ page }) => {
  for (const path of ["/", "/terms"]) {
    await page.goto(path);
    const social = page.getByRole("contentinfo").getByRole("list", { name: "Follow Cover Founder" });
    await expect(social.getByRole("link")).toHaveCount(3);
    for (const [name, href] of LINKS) {
      const link = social.getByRole("link", { name: new RegExp(`Cover Founder on ${name}`) });
      await expect(link).toBeVisible();
      await expect(link).toHaveAttribute("href", href);
      await expect(link).toHaveAttribute("target", "_blank");
      await expect(link).toHaveAttribute("rel", /noopener/);
    }
  }
});
