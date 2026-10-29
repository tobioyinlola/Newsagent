"""The industries a business picks at sign-up. Keys are stored; labels and examples are shown."""

from typing import Literal

Industry = Literal[
    "energy",
    "industrials",
    "consumer",
    "agriculture",
    "health_care",
    "financials",
    "real_estate",
    "technology",
    "government",
    "entertainment",
    "education",
]

INDUSTRIES: dict[str, tuple[str, str]] = {
    "energy": (
        "Energy",
        "Oil, gas, consumable fuels, energy equipment, chemicals, construction materials, metals and mining",
    ),
    "industrials": ("Industrials", "Aerospace, defense, machinery, transportation and commercial services"),
    "consumer": (
        "Consumer",
        "Retailers, apparel, automotive, leisure goods, beverage, tobacco and personal care products",
    ),
    "agriculture": ("Agriculture", "Food and farming"),
    "health_care": ("Health Care", "Pharmaceuticals, biotechnology and medical equipment"),
    "financials": ("Financials", "Banks, insurance companies and capital markets"),
    "real_estate": ("Real Estate", "Real estate investment trusts (REITs) and real estate development"),
    "technology": ("Technology", "Artificial intelligence, software, hardware, semiconductors and IT services"),
    "government": ("Government", "Politics and public institutions"),
    "entertainment": ("Entertainment", "Arts, music and sports"),
    "education": ("Education", "Schools, universities and learning"),
}
