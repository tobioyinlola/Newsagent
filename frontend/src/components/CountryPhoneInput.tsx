import { useEffect, useRef, useState } from "react";
import { getCountryCallingCode, parsePhoneNumberFromString, type CountryCode } from "libphonenumber-js";
import { nationalPhone, normalizePhone, phoneCountry, phoneCountries } from "../lib/phone";

type Props = { id: string; label: string; value: string; country?: string; error?: string; onChange: (number: string, country: string) => void };

export function CountryPhoneInput({ id, label, value, country: savedCountry, error, onChange }: Props) {
  const country = phoneCountry(value, savedCountry);
  const [local, setLocal] = useState(() => nationalPhone(value, country));
  const emitted = useRef(value);
  useEffect(() => {
    if (value !== emitted.current) { setLocal(nationalPhone(value, country)); emitted.current = value; }
  }, [value, country]);
  const emit = (raw: string, selected: CountryCode | "") => {
    emitted.current = normalizePhone(raw, selected);
    onChange(emitted.current, selected);
  };
  const errorId = `distribution-error-${id}`;
  return <fieldset className="min-w-0">
    <legend className="font-semibold">{label}</legend>
    <label className="sr-only" htmlFor={`${id}-country`}>{label} country</label>
    <select id={`${id}-country`} autoComplete={`section-${id} country`} value={country} aria-invalid={!!error && !country} aria-describedby={error ? errorId : `${id}-help`} className="mt-2 block min-h-12 w-full min-w-0 rounded-lg border border-ink bg-white px-3 font-normal" onChange={e => { const next = e.target.value as CountryCode | ""; const national = nationalPhone(value, country); setLocal(national); emit(national, next); }}>
      <option value="">Select country</option>
      {phoneCountries.map(c => <option key={c.code} value={c.code}>{c.name} (+{c.dial})</option>)}
    </select>
    <div className="mt-2 flex min-h-12 overflow-hidden rounded-lg border border-ink bg-white focus-within:ring-2 focus-within:ring-ink focus-within:ring-offset-2">
      <span aria-hidden="true" className="flex shrink-0 items-center border-r border-line bg-paper px-3 font-semibold">{country ? `+${getCountryCallingCode(country)}` : "+"}</span>
      <label className="sr-only" htmlFor={`${id}-number`}>{label}</label>
      <input id={`${id}-number`} type="tel" inputMode="tel" autoComplete={`section-${id} tel-national`} value={local} maxLength={40} placeholder="Enter phone number" aria-invalid={!!error} aria-describedby={error ? errorId : `${id}-help`} className="block min-h-12 w-full min-w-0 border-0 bg-transparent p-3 font-normal outline-none" onChange={e => {
        let raw = e.target.value; let next = country;
        if (raw.trim().startsWith("+")) {
          const parsed = parsePhoneNumberFromString(raw, { extract: false });
          if (parsed?.country) { next = parsed.country; raw = parsed.nationalNumber; }
        }
        setLocal(raw); emit(raw, next);
      }} />
    </div>
    <p id={`${id}-help`} className="mt-1 text-xs text-muted">Select the country, then enter the local number. You can also paste an international number.</p>
    {error && <p id={errorId} role="alert" className="mt-1 text-sm font-semibold text-red-800">{error}</p>}
  </fieldset>;
}
