#!/usr/bin/env python3
"""Validate schema.org JSON-LD against Google rich-result property rules.

  validate_jsonld.py page.html [more.html ...]       # extracts <script type="application/ld+json">
  validate_jsonld.py product.json                     # a .json / .jsonld file
  validate_jsonld.py - < snippet.json                 # stdin (JSON or HTML)
  validate_jsonld.py --list-types

Checks every typed node, including nested ones (offers, author, address, @graph):
required properties (error), recommended properties (warning), value formats
(ISO 8601 dates, absolute URLs, ISO 4217 currency, numeric price and rating),
@context, and known rich-result caveats.

This is an offline pre-flight check, not a replacement for Google's Rich Results Test.
Exit status: 0 = no errors (or no warnings with --strict), 1 = problems, 2 = input error.
Python 3.9+ standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser

# Each rule: required = list of alternatives ("a|b" means one of a or b),
# recommended = same syntax. "note" is printed once per type when present.
ARTICLE = {
    "required": [],
    "recommended": ["headline", "image", "datePublished", "dateModified", "author"],
}
LOCAL_BUSINESS = {
    "required": ["name", "address"],
    "recommended": ["telephone", "url", "openingHoursSpecification|openingHours", "geo", "image", "priceRange"],
}
RULES: dict[str, dict] = {
    "Article": ARTICLE,
    "NewsArticle": ARTICLE,
    "BlogPosting": ARTICLE,
    "TechArticle": ARTICLE,
    "Product": {
        "required": ["name", "offers|review|aggregateRating"],
        "recommended": ["image", "description", "sku|gtin|gtin8|gtin12|gtin13|gtin14|mpn", "brand"],
    },
    "Offer": {
        "required": ["price|priceSpecification", "priceCurrency|priceSpecification"],
        "recommended": ["availability", "url", "priceValidUntil", "itemCondition"],
    },
    "AggregateOffer": {"required": ["lowPrice", "priceCurrency"], "recommended": ["highPrice", "offerCount"]},
    "AggregateRating": {"required": ["ratingValue", "ratingCount|reviewCount"], "recommended": []},
    "Review": {"required": ["author", "reviewRating"], "recommended": ["datePublished"]},
    "Rating": {"required": ["ratingValue"], "recommended": ["bestRating", "worstRating"]},
    "FAQPage": {
        "required": ["mainEntity"],
        "recommended": [],
        "note": "Google shows FAQ rich results only for well-known government and health sites (since Aug 2023); the markup is still valid.",
    },
    "Question": {"required": ["name", "acceptedAnswer|suggestedAnswer"], "recommended": []},
    "Answer": {"required": ["text"], "recommended": []},
    "LocalBusiness": LOCAL_BUSINESS,
    "PostalAddress": {
        "required": [],
        "recommended": ["streetAddress", "addressLocality", "postalCode", "addressCountry"],
    },
    "GeoCoordinates": {"required": ["latitude", "longitude"], "recommended": []},
    "Organization": {"required": ["name"], "recommended": ["url", "logo", "sameAs"]},
    "Person": {"required": ["name"], "recommended": ["url|sameAs"]},
    "WebSite": {"required": ["name", "url"], "recommended": ["alternateName"]},
    "BreadcrumbList": {"required": ["itemListElement"], "recommended": []},
    "ListItem": {"required": ["position"], "recommended": []},
    "Event": {
        "required": ["name", "startDate", "location"],
        "recommended": [
            "endDate",
            "eventStatus",
            "eventAttendanceMode",
            "image",
            "description",
            "offers",
            "organizer",
            "performer",
        ],
    },
    "VideoObject": {
        "required": ["name", "thumbnailUrl", "uploadDate"],
        "recommended": ["description", "contentUrl|embedUrl", "duration"],
    },
    "ImageObject": {"required": ["contentUrl|url"], "recommended": []},
    "HowTo": {
        "required": ["name", "step"],
        "recommended": [],
        "note": "Google retired HowTo rich results in 2023; keep the markup only if other consumers use it.",
    },
}
# Nested nodes (author, publisher, brand...) are only checked for required properties,
# except these types, which normally live nested and whose recommendations matter.
NESTED_RECOMMENDED = {"Offer", "AggregateOffer", "PostalAddress", "Review", "Event"}
# Common LocalBusiness / Organization subtypes mapped to their parent rule.
LOCAL_SUBTYPES = """
    AutoRepair AutomotiveBusiness Bakery BarOrPub BeautySalon CafeOrCoffeeShop ChildCare Dentist
    DryCleaningOrLaundry Electrician EmergencyService EntertainmentBusiness FinancialService
    FoodEstablishment GeneralContractor GroceryStore HairSalon HealthAndBeautyBusiness
    HomeAndConstructionBusiness Hotel HousePainter HVACBusiness LegalService Locksmith
    LodgingBusiness MedicalBusiness MovingCompany Notary Physician Plumber ProfessionalService
    RealEstateAgent Restaurant RoofingContractor SportsActivityLocation Store TravelAgency
    VeterinaryCare AccountingService Attorney ClothingStore ElectronicsStore FurnitureStore
    HardwareStore Optician Pharmacy
""".split()
ORG_SUBTYPES = """
    Corporation EducationalOrganization NGO OnlineStore OnlineBusiness NewsMediaOrganization
""".split()
for _t in LOCAL_SUBTYPES:
    RULES.setdefault(_t, LOCAL_BUSINESS)
for _t in ORG_SUBTYPES:
    RULES.setdefault(_t, RULES["Organization"])

DATE_PROPS = {
    "datePublished",
    "dateModified",
    "dateCreated",
    "uploadDate",
    "startDate",
    "endDate",
    "validFrom",
    "validThrough",
    "priceValidUntil",
}
URL_PROPS = {"url", "logo", "thumbnailUrl", "contentUrl", "embedUrl", "sameAs", "item", "image", "mainEntityOfPage"}
NUMERIC_PROPS = {
    "price",
    "lowPrice",
    "highPrice",
    "ratingValue",
    "bestRating",
    "worstRating",
    "ratingCount",
    "reviewCount",
    "latitude",
    "longitude",
    "position",
}
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$")
ISO_DURATION = re.compile(r"^P(?!$)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+(\.\d+)?S)?)?$")
AVAILABILITY = {
    "InStock",
    "OutOfStock",
    "PreOrder",
    "BackOrder",
    "Discontinued",
    "InStoreOnly",
    "LimitedAvailability",
    "OnlineOnly",
    "PreSale",
    "SoldOut",
    "Reserved",
    "MadeToOrder",
}


def read_text(path: str, encoding: str = "utf-8", errors: str = "strict") -> str:
    with open(path, encoding=encoding, errors=errors) as fh:
        return fh.read()


class JsonLdExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.blocks: list[str] = []
        self._in = False
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "script" and dict(attrs).get("type", "").strip().lower() == "application/ld+json":
            self._in = True
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in:
            self._in = False
            self.blocks.append("".join(self._buf))

    def handle_data(self, data: str) -> None:
        if self._in:
            self._buf.append(data)


def types_of(node: dict) -> list[str]:
    t = node.get("@type")
    if isinstance(t, str):
        t = [t]
    if not isinstance(t, list):
        return []
    return [str(x).replace("https://schema.org/", "").replace("http://schema.org/", "") for x in t]


def has_value(node: dict, prop: str) -> bool:
    v = node.get(prop)
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return bool(v)
    return True


class Validator:
    def __init__(self) -> None:
        self.issues: list[dict] = []
        self.entities: list[dict] = []
        self._notes: set[str] = set()

    def add(self, severity: str, path: str, message: str) -> None:
        self.issues.append({"severity": severity, "path": path, "message": message})

    def check_root(self, data, path: str) -> None:
        items = data if isinstance(data, list) else [data]
        for i, item in enumerate(items):
            p = f"{path}[{i}]" if isinstance(data, list) else path
            if not isinstance(item, dict):
                self.add("error", p, "Top-level JSON-LD value must be an object or an array of objects.")
                continue
            ctx = item.get("@context")
            ctx_s = json.dumps(ctx) if ctx is not None else ""
            if "schema.org" not in ctx_s:
                self.add("error", p, 'Missing or non-schema.org @context (use "https://schema.org").')
            if "@graph" in item:
                graph = item["@graph"]
                if not isinstance(graph, list):
                    self.add("error", p, "@graph must be an array.")
                    continue
                for j, node in enumerate(graph):
                    self.check_node(node, f"{p}.@graph[{j}]", top=True)
            else:
                self.check_node(item, p, top=True)

    def check_node(self, node, path: str, top: bool = False, parent_prop: str = "") -> None:
        if not isinstance(node, dict):
            return
        tps = types_of(node)
        if not tps:
            if top and "@id" not in node:
                self.add("error", path, "Node has no @type.")
        label = "/".join(tps) or "(untyped)"
        here = f"{path} {label}" if tps else path
        if tps:
            self.entities.append({"path": path, "types": tps})
        only_ref = set(node) <= {"@id", "@type"} and "@id" in node
        for t in tps:
            rule = RULES.get(t)
            if not rule or only_ref:
                continue
            for alt in rule["required"]:
                if not any(has_value(node, a) for a in alt.split("|")):
                    self.add("error", here, f"Missing required property: {alt.replace('|', ' or ')}.")
            if top or t in NESTED_RECOMMENDED:
                for alt in rule["recommended"]:
                    if not any(has_value(node, a) for a in alt.split("|")):
                        self.add("warning", here, f"Missing recommended property: {alt.replace('|', ' or ')}.")
            if rule.get("note") and t not in self._notes:
                self._notes.add(t)
                self.add("notice", here, rule["note"])
            self.type_specific(t, node, here, top, parent_prop)
        self.check_formats(node, here)
        for prop, value in node.items():
            if prop.startswith("@"):
                continue
            vals = value if isinstance(value, list) else [value]
            for k, v in enumerate(vals):
                if isinstance(v, dict):
                    sub = f"{path}.{prop}" + (f"[{k}]" if isinstance(value, list) else "")
                    self.check_node(v, sub, parent_prop=prop)

    def type_specific(self, t: str, node: dict, here: str, top: bool, parent_prop: str) -> None:
        if t in ("Review", "AggregateRating") and top and not has_value(node, "itemReviewed"):
            self.add("error", here, f"Standalone {t} needs itemReviewed (or nest it inside the item it rates).")
        if t == "FAQPage":
            for q in node.get("mainEntity") if isinstance(node.get("mainEntity"), list) else [node.get("mainEntity")]:
                if isinstance(q, dict) and "Question" not in types_of(q):
                    self.add("error", here, "Every FAQPage mainEntity item must be a Question.")
        if t == "BreadcrumbList":
            items = node.get("itemListElement")
            items = items if isinstance(items, list) else [items]
            positions = []
            for idx, li in enumerate(items):
                if not isinstance(li, dict):
                    continue
                positions.append(li.get("position"))
                last = idx == len(items) - 1
                if not last and not has_value(li, "item"):
                    self.add(
                        "error",
                        f"{here}.itemListElement[{idx}]",
                        "ListItem needs item (URL) unless it is the last crumb.",
                    )
                if not has_value(li, "name") and not (
                    isinstance(li.get("item"), dict) and has_value(li["item"], "name")
                ):
                    self.add("error", f"{here}.itemListElement[{idx}]", "ListItem needs a name.")
            try:
                if [int(p) for p in positions] != list(range(1, len(positions) + 1)):
                    self.add("warning", here, f"Breadcrumb positions should be 1..n in order, got {positions}.")
            except (TypeError, ValueError):
                self.add("error", here, f"Breadcrumb positions must be integers, got {positions}.")
        if t in ("Offer", "AggregateOffer"):
            cur = node.get("priceCurrency")
            if isinstance(cur, str) and not re.fullmatch(r"[A-Z]{3}", cur):
                self.add("error", here, f"priceCurrency '{cur}' must be a 3-letter ISO 4217 code such as USD.")
            av = node.get("availability")
            if isinstance(av, str):
                name = av.rsplit("/", 1)[-1]
                if name not in AVAILABILITY:
                    self.add("error", here, f"availability '{av}' is not a schema.org ItemAvailability value.")
                elif not av.startswith(("https://schema.org/", "http://schema.org/")):
                    self.add("warning", here, f"Write availability as a full URL: https://schema.org/{name}.")
        if t in ("Article", "NewsArticle", "BlogPosting", "TechArticle"):
            author = node.get("author")
            for a in author if isinstance(author, list) else [author]:
                if isinstance(a, str):
                    self.add(
                        "warning",
                        here,
                        "author is a plain string; use a Person or Organization object with name and url.",
                    )
        if t == "AggregateRating":
            try:
                rv = float(node.get("ratingValue"))
                best = float(node.get("bestRating", 5))
                worst = float(node.get("worstRating", 1))
                if not worst <= rv <= best:
                    self.add(
                        "error",
                        here,
                        f"ratingValue {rv} is outside {worst}-{best} (set bestRating/worstRating if your scale differs).",
                    )
            except (TypeError, ValueError):
                pass
            for prop in ("ratingCount", "reviewCount"):
                v = node.get(prop)
                if v is not None:
                    try:
                        if int(float(v)) <= 0:
                            self.add("error", here, f"{prop} must be a positive number.")
                    except (TypeError, ValueError):
                        pass
        if t == "Event":
            mode = node.get("eventAttendanceMode", "")
            loc = node.get("location")
            locs = loc if isinstance(loc, list) else [loc]
            if isinstance(mode, str) and mode.endswith("OnlineEventAttendanceMode"):
                if not any(isinstance(x, dict) and "VirtualLocation" in types_of(x) for x in locs):
                    self.add("error", here, "Online events need a VirtualLocation with a url.")
            for x in locs:
                if isinstance(x, dict) and "Place" in types_of(x) and not has_value(x, "address"):
                    self.add("error", here, "Event Place needs an address.")
        if t == "VideoObject" and isinstance(node.get("duration"), str) and not ISO_DURATION.match(node["duration"]):
            self.add("error", here, f"duration '{node['duration']}' is not ISO 8601 (e.g. PT1M33S).")

    def check_formats(self, node: dict, here: str) -> None:
        for prop, value in node.items():
            vals = value if isinstance(value, list) else [value]
            for v in vals:
                if prop in DATE_PROPS and isinstance(v, str) and not ISO_DATE.match(v.strip()):
                    self.add("error", here, f"{prop} '{v}' is not ISO 8601 (YYYY-MM-DD or YYYY-MM-DDThh:mm:ss+hh:mm).")
                if prop in URL_PROPS and isinstance(v, str) and v and not re.match(r"^https?://", v):
                    self.add("warning", here, f"{prop} '{v}' should be an absolute http(s) URL.")
                if prop in NUMERIC_PROPS and isinstance(v, str):
                    try:
                        float(v)
                    except ValueError:
                        self.add(
                            "error",
                            here,
                            f"{prop} '{v}' must be a number without currency symbols or thousands separators.",
                        )
                if prop == "price" and isinstance(v, (int, float)) and v < 0:
                    self.add("error", here, "price is negative.")


def load_blocks(source: str, text: str) -> list[tuple[str, str]]:
    stripped = text.lstrip()
    if stripped.startswith(("{", "[")):
        return [(source, text)]
    ex = JsonLdExtractor()
    ex.feed(text)
    return [(f"{source}#jsonld{i + 1}", b) for i, b in enumerate(ex.blocks)]


def validate_text(source: str, text: str) -> dict:
    v = Validator()
    blocks = load_blocks(source, text)
    if not blocks:
        v.add("warning", source, "No JSON-LD blocks found.")
    for name, raw in blocks:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            v.add("error", name, f"Invalid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}.")
            continue
        v.check_root(data, name)
    return {"source": source, "blocks": len(blocks), "entities": v.entities, "issues": v.issues}


def render_text(results: list[dict]) -> str:
    out = []
    for res in results:
        types = sorted({t for e in res["entities"] for t in e["types"]})
        out.append(f"{res['source']}: {res['blocks']} block(s); types: {', '.join(types) or '-'}")
        if not res["issues"]:
            out.append("  OK - no issues")
        for sev in ("error", "warning", "notice"):
            for i in res["issues"]:
                if i["severity"] == sev:
                    out.append(f"  {sev.upper():<8} {i['path']}: {i['message']}")
        out.append("")
    return "\n".join(out).rstrip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Offline JSON-LD validator for Google rich-result property rules.",
        epilog="Exit codes: 0 ok, 1 errors (or warnings with --strict), 2 input error.",
    )
    ap.add_argument("files", nargs="*", help="HTML, .json or .jsonld files; '-' for stdin")
    ap.add_argument("--json", action="store_true", help="print JSON")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    ap.add_argument("--list-types", action="store_true", help="print the supported types and their rules")
    args = ap.parse_args(argv)
    if args.list_types:
        base = {k: v for k, v in RULES.items() if k not in LOCAL_SUBTYPES and k not in ORG_SUBTYPES}
        if args.json:
            print(json.dumps(base, indent=2))
        else:
            for t, r in base.items():
                print(
                    f"{t}\n  required:    {', '.join(r['required']) or '-'}\n  recommended: {', '.join(r['recommended']) or '-'}"
                )
            print(f"\nLocalBusiness subtypes: {', '.join(LOCAL_SUBTYPES)}")
        return 0
    if not args.files:
        ap.error("give at least one file (or --list-types)")
    results = []
    for f in args.files:
        try:
            text = sys.stdin.read() if f == "-" else read_text(f, encoding="utf-8-sig")
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        results.append(validate_text("stdin" if f == "-" else f, text))
    print(json.dumps(results, indent=2) if args.json else render_text(results))
    bad = {"error", "warning"} if args.strict else {"error"}
    return 1 if any(i["severity"] in bad for r in results for i in r["issues"]) else 0


if __name__ == "__main__":
    sys.exit(main())
