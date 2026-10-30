import { getCountries, getCountryCallingCode, isSupportedCountry, parsePhoneNumberFromString, type CountryCode } from "libphonenumber-js";

const countryNames = new Intl.DisplayNames(["en"], { type: "region" });
export const phoneCountries = getCountries().map(code => ({ code, name: countryNames.of(code) ?? code, dial: getCountryCallingCode(code) })).sort((a, b) => a.name.localeCompare(b.name));

export function phoneCountry(value: string, saved?: string): CountryCode | "" {
  if (saved && isSupportedCountry(saved)) return saved as CountryCode;
  return value.trim().startsWith("+") ? parsePhoneNumberFromString(value, { extract: false })?.country ?? "" : "";
}

export function nationalPhone(value: string, country: CountryCode | ""): string {
  if (!value.trim().startsWith("+")) return value;
  const parsed = parsePhoneNumberFromString(value, { ...(country ? { defaultCountry: country } : {}), extract: false });
  return parsed?.nationalNumber ?? value;
}

export function normalizePhone(value: string, country: CountryCode | ""): string {
  if (!value.trim()) return "";
  if (!/^[+()0-9 .-]+$/.test(value)) return value;
  return parsePhoneNumberFromString(value, { ...(country ? { defaultCountry: country } : {}), extract: false })?.number ?? value;
}

export function validPhone(value: string, savedCountry?: string): boolean {
  const country = phoneCountry(value, savedCountry);
  if (!country || !/^[+()0-9 .-]+$/.test(value)) return false;
  const parsed = parsePhoneNumberFromString(value, { defaultCountry: country, extract: false });
  return !!parsed?.isValid() && parsed.countryCallingCode === getCountryCallingCode(country);
}
