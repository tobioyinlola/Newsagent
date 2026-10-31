import { useEffect, useRef, useState } from "react";
import { getCountryCallingCode, parsePhoneNumberFromString, type CountryCode } from "libphonenumber-js";
import { nationalPhone, normalizePhone, phoneCountry, phoneCountries } from "../lib/phone";

type Props = { id: string; label: string; value: string; country?: string; error?: string; onChange: (number: string, country: string) => void };
const flag = (code: string) => String.fromCodePoint(...[...code].map(c => 127397 + c.charCodeAt(0)));

export function CountryPhoneInput({ id, label, value, country: savedCountry, error, onChange }: Props) {
  const country = phoneCountry(value, savedCountry);
  const [local, setLocal] = useState(() => nationalPhone(value, country));
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [active, setActive] = useState(0);
  const root = useRef<HTMLFieldSetElement>(null);
  const picker = useRef<HTMLButtonElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const numberInput = useRef<HTMLInputElement>(null);
  const emitted = useRef(value);
  const query = search.trim().toLowerCase();
  const countries = phoneCountries.filter(c => `${c.name} ${c.code} +${c.dial}`.toLowerCase().includes(query));
  const selectedName = phoneCountries.find(c => c.code === country)?.name;
  useEffect(() => {
    if (value !== emitted.current) { setLocal(nationalPhone(value, country)); emitted.current = value; }
  }, [value, country]);
  useEffect(() => {
    if (!open) return;
    searchInput.current?.focus();
    const outside = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  useEffect(() => { if (open) document.getElementById(`${id}-country-option-${active}`)?.scrollIntoView({ block: "nearest" }); }, [active, open, id]);
  const emit = (raw: string, selected: CountryCode | "") => {
    emitted.current = normalizePhone(raw, selected);
    onChange(emitted.current, selected);
  };
  const pick = (next: CountryCode) => {
    const national = nationalPhone(value, country);
    setLocal(national); emit(national, next); setOpen(false); numberInput.current?.focus();
  };
  const errorId = `distribution-error-${id}`;
  return <fieldset ref={root} className="relative min-w-0" onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false); }} onKeyDown={e => { if (e.key === "Escape" && open) { e.preventDefault(); setOpen(false); picker.current?.focus(); } }}>
    <legend className="font-semibold">{label}</legend>
    <div className={`mt-2 flex min-h-13 rounded-lg border bg-white focus-within:ring-2 focus-within:ring-brand-purple focus-within:ring-offset-2 ${error ? "border-red-700" : "border-ink"}`}>
      <button ref={picker} type="button" aria-label={`${label} country`} aria-haspopup="dialog" aria-expanded={open} aria-controls={`${id}-country-picker`} title={selectedName || "Choose country"} className="flex min-w-28 shrink-0 items-center justify-center gap-2 rounded-l-lg border-r border-line bg-paper px-3 text-sm font-semibold hover:bg-lime-tint" onClick={() => { setSearch(""); setActive(0); setOpen(!open); }}>
        <span aria-hidden="true">{country ? flag(country) : "🌐"}</span><span>{country ? `+${getCountryCallingCode(country)}` : "Country"}</span><span aria-hidden="true" className="text-xs">▾</span>
      </button>
      <label className="sr-only" htmlFor={`${id}-number`}>{label}</label>
      <input ref={numberInput} id={`${id}-number`} type="tel" inputMode="tel" autoComplete={`section-${id} tel-national`} value={local} maxLength={40} placeholder="Phone number" aria-invalid={!!error} aria-describedby={error ? errorId : `${id}-help`} className="block min-h-13 w-full min-w-0 rounded-r-lg border-0 bg-transparent p-3 font-normal outline-none" onFocus={() => setOpen(false)} onChange={e => {
        let raw = e.target.value; let next = country;
        if (raw.trim().startsWith("+")) {
          const parsed = parsePhoneNumberFromString(raw, { extract: false });
          if (parsed?.country) { next = parsed.country; raw = parsed.nationalNumber; }
        }
        setLocal(raw); emit(raw, next);
      }} />
    </div>
    {open && <div id={`${id}-country-picker`} role="dialog" aria-label="Choose phone country" className="absolute left-0 right-0 z-30 mt-2 overflow-hidden rounded-xl border border-line bg-white p-2 shadow-xl">
      <label className="sr-only" htmlFor={`${id}-country-search`}>Search countries</label>
      <input ref={searchInput} id={`${id}-country-search`} role="combobox" aria-expanded="true" aria-controls={`${id}-countries`} aria-autocomplete="list" aria-activedescendant={countries[active] ? `${id}-country-option-${active}` : undefined} autoComplete="off" placeholder="Search country or calling code" value={search} className="min-h-11 w-full rounded-lg border border-line bg-paper px-3 text-sm" onChange={e => { setSearch(e.target.value); setActive(0); }} onKeyDown={e => {
        if (e.key === "ArrowDown") { e.preventDefault(); setActive(n => Math.min(n + 1, countries.length - 1)); }
        if (e.key === "ArrowUp") { e.preventDefault(); setActive(n => Math.max(n - 1, 0)); }
        if (e.key === "Enter" && countries[active]) { e.preventDefault(); pick(countries[active].code); }
      }} />
      <ul id={`${id}-countries`} role="listbox" aria-label="Countries" className="mt-2 max-h-60 overflow-y-auto overscroll-contain">
        {countries.map((c, index) => <li key={c.code} role="none"><button id={`${id}-country-option-${index}`} type="button" role="option" aria-selected={country === c.code} className={`flex min-h-11 w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-lime-tint ${active === index ? "bg-lime-tint" : ""}`} onMouseEnter={() => setActive(index)} onClick={() => pick(c.code)}><span aria-hidden="true">{flag(c.code)}</span><span className="min-w-0 flex-1">{c.name}</span><span className="shrink-0 text-muted">+{c.dial}</span></button></li>)}
      </ul>
      {!countries.length && <p role="status" className="p-3 text-sm text-muted">No matching countries. Try a country name or calling code.</p>}
    </div>}
    <p id={`${id}-help`} className="mt-1 text-xs text-muted">Choose your country and enter your number, or paste a full international number.</p>
    {error && <p id={errorId} role="alert" className="mt-1 text-sm font-semibold text-red-800">{error}</p>}
  </fieldset>;
}
