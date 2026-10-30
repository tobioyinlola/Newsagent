export type CardDetails = { first_name: string; last_name: string; number: string; expiry: string; cvv: string; address_line_one: string; city: string; state: string; country: string; zip: string };
export const emptyCard: CardDetails = { first_name: "", last_name: "", number: "", expiry: "", cvv: "", address_line_one: "", city: "", state: "", country: "", zip: "" };

export function expiryParts(value: string): { month: string; year: string } | null {
  const match = /^(0?[1-9]|1[0-2])\s*\/\s*(\d{2}|\d{4})$/.exec(value.trim());
  return match ? { month: match[1].padStart(2, "0"), year: match[2].length === 2 ? `20${match[2]}` : match[2] } : null;
}
export function cardErrors(card: CardDetails, now = new Date()): Partial<Record<keyof CardDetails, string>> {
  const errors: Partial<Record<keyof CardDetails, string>> = {};
  const number = card.number.replace(/[ -]/g, "");
  let sum = 0;
  for (let i = number.length - 1, double = false; i >= 0; i--, double = !double) { let digit = Number(number[i]); if (double) { digit *= 2; if (digit > 9) digit -= 9; } sum += digit; }
  if (!/^[1-9]\d{12,18}$/.test(number) || sum % 10 !== 0) errors.number = "Enter a valid card number.";
  const expiry = expiryParts(card.expiry);
  if (!expiry || Number(expiry.year) < now.getFullYear() || (Number(expiry.year) === now.getFullYear() && Number(expiry.month) < now.getMonth() + 1)) errors.expiry = "Enter a valid, unexpired date (MM/YY).";
  if (!/^\d{3,4}$/.test(card.cvv)) errors.cvv = "Enter the 3- or 4-digit security code.";
  for (const key of ["first_name", "last_name", "address_line_one", "city", "state"] as const) if (!card[key].trim()) errors[key] = "This field is required.";
  if (!/^[A-Z]{2}$/.test(card.country)) errors.country = "Enter a two-letter country code, for example NG, CA or US.";
  return errors;
}

export async function encryptCard(card: CardDetails, pem: string): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new Error("Card payments require a secure browser connection. Please use HTTPS.");
  const decoded = atob(pem.replace(/-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----|\s/g, ""));
  const key = await crypto.subtle.importKey("spki", Uint8Array.from(decoded, c => c.charCodeAt(0)), { name: "RSA-OAEP", hash: "SHA-256" }, false, ["encrypt"]);
  const expiry = expiryParts(card.expiry);
  if (!expiry) throw new Error("Enter a valid expiry date.");
  const payload = new TextEncoder().encode(JSON.stringify({ card_number: card.number.replace(/[ -]/g, ""), expiration_month: expiry.month, expiration_year: expiry.year, cvv: card.cvv, card_holder_name: `${card.first_name.trim()} ${card.last_name.trim()}` }));
  const max = (key.algorithm as RsaHashedKeyAlgorithm).modulusLength / 8 - 66;
  if (payload.length > max) throw new Error("The name on the card is too long for this payment method. Please use the shorter name printed on your card.");
  const encrypted = await crypto.subtle.encrypt({ name: "RSA-OAEP" }, key, payload);
  return btoa(String.fromCharCode(...new Uint8Array(encrypted)));
}
