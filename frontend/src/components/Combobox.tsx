import { useId, useState } from "react";
import { inputCls } from "./ui";

// A text box with a list to pick from: type to narrow it down, pick with the mouse or the arrow keys. With `strict` the value
// must be one of the options (countries); otherwise anything typed is kept (cities, since no list has every town).
export function Combobox({ id, value, onChange, options, required, placeholder, strict, autoComplete }: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  required?: boolean;
  placeholder?: string;
  strict?: boolean;
  autoComplete?: string;
}) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const q = value.trim().toLowerCase();
  const shown = (q ? [...options.filter((o) => o.toLowerCase().startsWith(q)), ...options.filter((o) => !o.toLowerCase().startsWith(q) && o.toLowerCase().includes(q))] : options).slice(0, 60);
  const pick = (v: string) => { onChange(v); setOpen(false); };
  const invalid = strict && value !== "" && !options.includes(value);
  return (
    <div className="relative">
      <input
        id={id}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete={autoComplete ?? "off"}
        required={required}
        placeholder={placeholder}
        className={inputCls}
        value={value}
        onChange={(e) => { onChange(e.target.value); setOpen(true); setActive(0); }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, shown.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          else if (e.key === "Enter" && open && shown[active]) { e.preventDefault(); pick(shown[active]); }
          else if (e.key === "Escape") setOpen(false);
        }}
        ref={(el) => el?.setCustomValidity(invalid ? "Pick one from the list." : "")}
      />
      {open && shown.length > 0 && (
        <ul id={listId} role="listbox" className="absolute z-20 mt-1 max-h-60 w-full overflow-auto rounded-sm border-2 border-ink bg-white text-sm shadow-lg">
          {shown.map((o, i) => (
            <li key={o} role="option" aria-selected={i === active} className={`cursor-pointer px-3 py-2 ${i === active ? "bg-brand-green/40" : ""}`} onMouseDown={(e) => { e.preventDefault(); pick(o); }} onMouseEnter={() => setActive(i)}>{o}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
