"""The media packages as first written down in "Cover Founder Regional Media Packages & BF/CM Offers" (November 2026).

Prices are the document's. A package with no US-dollar price (`usd` is None) is shown with its local price but is quoted, not sold in the app,
until the dollar price is set in the admin. `ids` are the outlets we hold in our own catalogue (None: not held, the team arranges it).
"""

from datetime import UTC, datetime

# The Black Friday and Cyber Monday campaign: 27 to 30 November 2026, West Africa time (the Nigeria office).
CAMPAIGN_START = datetime(2026, 11, 26, 23, 0, tzinfo=UTC)  # 27 Nov 00:00 WAT
CAMPAIGN_END = datetime(2026, 11, 30, 22, 59, 59, tzinfo=UTC)  # 30 Nov 23:59:59 WAT

# name in the document -> outlet id in our catalogue
CATALOG = {
    "Techbullion.com": "54", "TechBullion": "54", "Techpoint Africa": "2", "Vanguard Newspaper": "27", "ThisDay Newspaper": "28",
    "Tribune": "23", "AIT News": "50", "Big News Network": "58", "Tech Cabal": "5", "The Guardian": "29", "TVC News": "51",
    "USAToday.com": "56", "USA Today": "56", "Punch": "30", "Nairametrics": "3", "Business Insider": "18", "Business Outstanders": "57",
    "USAWire": "61", "Barchart": "20", "Barchart.com": "20", "Benzinga.com": "22", "Newsbreak.com": "60", "Associated Press": "95",
    "The Globe and Mail": "21", "Toronto Sun": "64", "Toronto Star": "62", "National Post": "67", "Canada-Wide Newswire": "69",
    "Techround UK": "75", "TechRound UK": "75", "Business Matters UK": "73", "London Loves Business": "72", "The Sun (UK)": "70",
    "European Business Review": "79", "Mashable Netherlands": "78", "Portugal News": "82", "Vanity Fair Germany": "77",
    "Forbes Liechtenstein": "81", "Arabian Startup": "91", "Dubai Weekly": "90", "Qatar Tribune": "89", "Gulf Business": "83",
    "Forbes Middle East": "84", "Arabian Business": "85", "Gulf News": "88", "Gulf Times": "87",
}


def ids_for(names: list[str]) -> list[str]:
    out: list[str] = []
    for n in names:
        i = CATALOG.get(n)
        if i and i not in out:
            out.append(i)
    return out


def _p(slug, kind, region, name, usd, outlets=(), *, local=None, ideal="", note="", includes=(), standard=None, slots=None, campaign="", window=False):
    names = list(outlets)
    return {
        "slug": slug, "kind": kind, "region": region, "campaign": campaign, "name": name, "usd_price": usd, "standard_usd": standard,
        "local_prices": local or {}, "outlet_names": names, "outlet_ids": ids_for(names), "includes": list(includes), "ideal_for": ideal,
        "note": note, "slots_total": slots, "slots_taken": 0, "starts_at": CAMPAIGN_START if window else None,
        "ends_at": CAMPAIGN_END if window else None,
    }


PACKAGES: list[dict] = [
    # ---- Nigeria and West Africa
    _p("pre-seed-nigeria", "regional", "nigeria", "Pre-Seed Package (Nigeria)", "365.00", ["Techpoint Africa", "Vanguard Newspaper", "ThisDay Newspaper"],
       local={"NGN": "506000"}, ideal="Pre-seed founders announcing their first launch or milestone to a Nigerian audience."),
    _p("nigeria-startup-launch", "regional", "nigeria", "The Nigeria Startup Launch Package", "651.57", ["Techbullion.com", "Techpoint Africa", "Tribune", "AIT News"],
       local={"NGN": "912203.49"}, ideal="Early-stage Nigerian startups announcing a launch, product, partnership or business milestone."),
    _p("nigeria-startup-growth", "regional", "nigeria", "The Nigeria Startup Growth Package", "1198.61", ["Big News Network", "Tech Cabal", "The Guardian", "TVC News", "USAToday.com"],
       local={"NGN": "1678059.10"}, ideal="Startups raising capital, expanding operations, announcing partnerships or building investor confidence."),
    _p("nigeria-market-leadership", "regional", "nigeria", "The Nigeria Market Leadership Package", "1918.86", ["Techbullion.com", "Business Insider Africa", "Tech Cabal", "Punch", "AIT News", "USAToday.com"],
       local={"NGN": "2686405.04"}, ideal="Established businesses, major announcements, executive visibility and market expansion."),
    # ---- Africa-wide
    _p("africa-startup-entry", "regional", "africa", "The Africa Startup Entry Package", "1533.24", ["Techbullion.com", "Business Insider Africa", "Techpoint Africa", "The Guardian", "USAToday.com"],
       local={"GHS": "18022", "KES": "199199", "UGX": "6423555"}, ideal="Startups seeking broader African visibility through regional business, technology and Nigerian media.",
       note="Placements in Ghana, Kenya and Uganda media are quoted separately."),
    _p("africa-business-expansion", "regional", "africa", "The Africa Business Expansion Package", "1905.30", ["Techbullion.com", "Business Insider Africa", "Tech Cabal", "Nairametrics", "The Guardian", "Business Insider"],
       local={"GHS": "22396", "KES": "247537", "UGX": "7982312"}, ideal="Businesses expanding across African markets and building regional recognition.",
       note="Placements in Ghana, Kenya and Uganda media are quoted separately."),
    # ---- United States
    _p("usa-startup-visibility", "regional", "us", "The USA Startup Visibility Package", "554.58", ["TechBullion", "Business Outstanders", "USAWire", "Big News Network", "Barchart"],
       ideal="Startups seeking an initial US media presence and business awareness."),
    _p("usa-entrepreneurship", "regional", "us", "The USA Entrepreneurship Package", "1109.16", ["Techbullion.com", "Barchart.com", "Business Insider", "USAToday.com", "Benzinga.com", "Newsbreak.com"],
       ideal="Founders and growing companies seeking wider US business and technology visibility."),
    _p("usa-executive-authority", "regional", "us", "The USA Executive Authority Package", "7690.41", ["CNN.com", "Techbullion.com", "Business Insider", "USAToday.com", "Associated Press"],
       ideal="CEOs, founders and senior executives seeking premium international digital media visibility.",
       note="CNN is not included as a guaranteed placement. A confirmed interview or paid opportunity must be agreed separately."),
    # ---- Canada
    _p("canada-startup-entry", "regional", "canada", "The Canadian Startup Entry Package", "961.74", ["Techbullion.com", "The Globe and Mail", "Toronto Sun"],
       local={"CAD": "1377.02"}, ideal="Startups introducing their businesses to the Canadian market."),
    _p("canada-business-growth", "regional", "canada", "The Canadian Business Growth Package", "9480.51",
       ["Techbullion.com", "Toronto Star", "National Post", "Canada-Wide Newswire", "Benzinga.com"],
       local={"CAD": "13574.19"}, ideal="Growing companies and organisations seeking broader Canadian and international business visibility.",
       note="The Canada-Wide Newswire release goes to 50 outlets, with 250 words, 1 logo and 1 picture."),
    # ---- United Kingdom and Europe
    _p("uk-startup-visibility", "regional", "uk_europe", "The UK Startup Visibility Package", None, ["TechRound UK", "Business Matters UK", "London Loves Business"],
       local={"GBP": "530"}, ideal="Startups and entrepreneurs looking to introduce themselves to the UK business community."),
    _p("uk-business", "regional", "uk_europe", "The UK Business Package", "25896.78", ["Techbullion.com", "Techround UK", "The Sun (UK)"],
       local={"GBP": "19678.19"}, ideal="Startups and entrepreneurs seeking UK technology and national newspaper visibility."),
    _p("european-business-expansion", "regional", "uk_europe", "The European Business Expansion Package", "5545.80",
       ["European Business Review", "Mashable Netherlands", "Portugal News", "Vanity Fair Germany", "Forbes Liechtenstein"],
       local={"EUR": "5048.79", "CHF": "4670.78"}, ideal="Businesses looking to establish a presence across selected European markets."),
    # ---- Middle East
    _p("middle-east-startup-entry", "regional", "middle_east", "The Middle East Startup Entry Package", None, ["Arabian Startup", "Dubai Weekly", "Qatar Tribune"],
       local={"AED": "1820", "QAR": "1805"}, ideal="Startups entering the Gulf region and introducing their products or services."),
    _p("middle-east-business-authority", "regional", "middle_east", "The Middle East Business Authority Package", None,
       ["Gulf Business", "Forbes Middle East", "Arabian Business", "Gulf News", "Gulf Times"],
       local={"AED": "9165", "QAR": "9095"}, ideal="Established businesses, executives, investors and companies seeking visibility in the Middle East."),
    # ---- Organisations and institutions
    _p("accelerator-incubator-partnership", "organisation", "organisation", "The Accelerator & Incubator Media Partnership", "5000.00",
       includes=["Media visibility packages for 10 selected portfolio startups", "Regional press distribution", "Individual founder and business stories", "Dedicated campaign coordination", "Consolidated coverage report"],
       ideal="Accelerators, incubators, venture studios and startup programmes.", note="The number of stories, distribution slots and placements is agreed in a service schedule."),
    _p("corporate-visibility-partnership", "organisation", "organisation", "The Corporate Visibility Partnership", "10000.00",
       includes=["Media campaigns for up to 20 executives, business units or portfolio companies", "Regional and international media opportunities", "Corporate announcements and leadership stories", "Coordinated press distribution", "Campaign performance report"],
       ideal="Corporates, investment firms, holding companies and business associations.", note="The number of stories, distribution slots and placements is agreed in a service schedule."),
    _p("global-portfolio-partnership", "organisation", "organisation", "The Global Portfolio Media Partnership", "25000.00",
       includes=["Media visibility for up to 50 startups or portfolio companies", "Access to selected regional media packages", "Founder and executive storytelling", "Multi-market distribution opportunities", "Dedicated account management", "Consolidated reporting and campaign reviews"],
       ideal="International accelerators, venture capital firms, startup networks and investment organisations.",
       note="The number of stories, distribution slots and placements is agreed in a service schedule."),
    # ---- Black Friday (27 to 30 November 2026)
    _p("bf-startup-visibility-deal", "campaign", "campaign", "The Startup Visibility Deal", "651.57", ["Techbullion.com", "Techpoint Africa", "Tribune", "AIT News"], campaign="black_friday",
       local={"NGN": "912203.49"}, slots=20, window=True, ideal="Startups and small businesses.",
       includes=["One professionally prepared business story", "Four media placements across technology, newspaper and television categories", "Digital coverage report"],
       note="Limited slots at the published package price. This is a limited-slot offer, not a discount."),
    _p("bf-international-founder-deal", "campaign", "campaign", "The International Founder Visibility Deal", "995.00",
       ["TechBullion", "Business Outstanders", "USAWire", "Big News Network", "Barchart", "USA Today"], campaign="black_friday", standard="1495.00",
       slots=10, window=True, ideal="Startups and founders seeking international visibility.",
       includes=["Professionally prepared founder or company story", "Six selected US digital media placements", "Digital coverage report"]),
    _p("bf-executive-spotlight-deal", "campaign", "campaign", "The Executive Spotlight Deal", "7690.41",
       ["CNN.com", "Techbullion.com", "Business Insider", "USA Today", "Associated Press"], campaign="black_friday", standard="15000.00",
       slots=10, window=True, ideal="CEOs, founders and senior executives.",
       includes=["Executive profile development", "Five selected digital media placements", "Dedicated campaign coordination"],
       note="First 10 confirmed clients only. CNN.com is a digital placement, not a television interview."),
    # ---- Cyber Monday
    _p("cm-two-market-deal", "campaign", "campaign", "The Two-Market Visibility Deal", "1495.00",
       ["Techbullion.com", "Techpoint Africa", "Tribune", "AIT News", "Business Outstanders", "USAWire", "Big News Network", "Barchart"],
       campaign="cyber_monday", standard="2495.00", slots=15, window=True, ideal="Startups and businesses expanding internationally.",
       includes=["Nigeria Startup Launch and USA Startup Visibility media combinations", "One founder or company story", "Selected placements in Nigeria and the United States", "Digital coverage report"]),
    _p("cm-startup-portfolio-deal", "campaign", "campaign", "The Startup Portfolio Deal", None, campaign="cyber_monday", slots=5, window=True,
       ideal="Accelerators, incubators and investment firms.",
       includes=["Media visibility for up to 10 startups", "Individual business stories", "Selected regional media placements", "Campaign coordination", "Consolidated report"],
       note="Only five institutional slots available. Custom quote."),
]
