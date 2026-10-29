// Builds public/geo/countries.json and one public/geo/<ISO>.json of city names per country, for the sign-up pickers.
// Run once (pnpm gen:geo) and commit the output; the app loads only the country that was picked.
import { writeFileSync, mkdirSync } from "node:fs";
import { City, Country } from "country-state-city";

mkdirSync("public/geo", { recursive: true });
const countries = Country.getAllCountries().map((c) => ({ code: c.isoCode, name: c.name })).sort((a, b) => a.name.localeCompare(b.name));
writeFileSync("public/geo/countries.json", JSON.stringify(countries));
let total = 0;
for (const c of countries) {
  const names = [...new Set((City.getCitiesOfCountry(c.code) ?? []).map((x) => x.name.trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  if (!names.length) continue;
  writeFileSync(`public/geo/${c.code}.json`, JSON.stringify(names));
  total += names.length;
}
console.log(`${countries.length} countries, ${total} cities`);
