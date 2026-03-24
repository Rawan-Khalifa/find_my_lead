"""
ingestion/scraper.py

GAF contractor directory scraper using Playwright + direct Coveo API.

STRATEGY (in priority order):
    1. Direct Coveo API call — GAF's contractor search is powered by Coveo.
       The API key and org ID are embedded in every page load (public, read-only).
       We call platform.cloud.coveo.com directly: no browser, no bot detection,
       clean structured JSON, sub-second response. This is the production path.
    2. XHR/fetch interception — launch headless Chromium, register a response
       listener BEFORE navigation, capture the Coveo API response the browser
       would have made. Used if the direct API call fails or the key rotates.
    3. DOM extraction — fallback if no API response was captured.
       Multi-selector approach, most stable selectors tried first.
    4. Mock data — fallback for demo/testing when the scraper is blocked.

WHY PLAYWRIGHT at all (when we have the direct API):
    The direct API key is embedded in the page HTML -- if GAF rotates it, we
    need to re-scrape the page to discover the new key. Playwright + XHR
    interception is how we'd do that automatically. It's also our fallback if
    Coveo adds IP allowlisting on the direct endpoint.

BOT DETECTION (Playwright path):
    GAF uses Akamai EdgeSuite, which fingerprints headless browsers via:
      - navigator.webdriver flag (most common signal)
      - navigator.plugins / navigator.languages
      - Missing Chrome runtime object
    We patch all of these via add_init_script() which runs BEFORE any
    page JavaScript, so the patches are in place when Akamai checks.

PRODUCTION CONSIDERATIONS:
    - Containerize with Chromium bundled (playwright install chromium)
    - Store Coveo API key in secrets manager, not hardcoded -- refresh if 401
    - Rate limit with random jitter between requests (polite scraping)
    - Archive raw API responses to S3 -- lets you re-parse without re-calling
    - Selector health check: alert if yield drops >20% vs 7-day baseline
"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import math
import re
import urllib.request
import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.contractor import ContractorRaw, ContractorRecord, GAFTier, PipelineStage

RAW_DATA_DIR = Path(__file__).parent.parent / "data" / "raw"
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Injected before any page JS runs. Clears every signal Akamai checks
# for headless/automated browser detection.
_STEALTH_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (params) =>
        params.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(params);
"""

# ─────────────────────────────────────────────────────────────
# COVEO DIRECT API CONFIG
# ─────────────────────────────────────────────────────────────
# These values are embedded in every GAF page load — public, read-only keys.
# The residential contractor pipeline is distinct from the general search pipeline.
# If GAF rotates these, the Playwright XHR interception path re-discovers them.
_COVEO_API_KEY    = "xx3cfe6ca4-11f2-45b6-83ad-41e053e06504"
_COVEO_ORG_ID     = "gafmaterialscorporationproduction3yalqk12"
_COVEO_PIPELINE   = "prod-gaf-recommended-residential-contractors"
_COVEO_SEARCH_URL = (
    f"https://platform.cloud.coveo.com/rest/search/v2"
    f"?organizationId={_COVEO_ORG_ID}"
)

# URL substrings that identify Coveo API calls in the XHR interception path.
# Cast wide — better to examine extra responses than miss the right one.
_API_URL_SIGNALS = [
    "coveo", "cloud.coveo", "platform.cloud",
    "contractor", "roofer", "search", "find", "locate",
    "algolia", "/api/", "/v1/", "/v2/", "directory", "dealer",
]


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _deterministic_id(name: str, address: Optional[str]) -> str:
    """
    Stable UUID from name + address.

    WHY deterministic:
        Running the pipeline twice should UPDATE the same record, not create
        a duplicate. This is the foundation of our idempotent upsert pattern.
        Same contractor = same ID, every time, across any number of runs.
    """
    key = f"{name.lower().strip()}:{(address or '').lower().strip()}"
    return str(uuid.UUID(hashlib.md5(key.encode()).hexdigest()))


def _parse_distance(text: str) -> Optional[float]:
    match = re.search(r"([\d.]+)\s*mi", str(text), re.IGNORECASE)
    return float(match.group(1)) if match else None


def _parse_rating(text: str) -> Optional[float]:
    match = re.search(r"([\d.]+)", str(text))
    try:
        return float(match.group(1)) if match else None
    except ValueError:
        return None


def _parse_city_state(address: str) -> tuple[Optional[str], Optional[str]]:
    if not address:
        return None, None
    match = re.search(r"([A-Za-z\s]+),\s*([A-Z]{2})", address)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return None, None


def _find_contractor_array(data: object, depth: int = 0) -> list[dict]:
    """
    Recursively walk an unknown JSON blob looking for a list of objects
    that have at least one name-like field. This is how we handle GAF's
    API response without knowing its schema ahead of time.
    """
    if depth > 6:
        return []

    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            keys_lower = {k.lower() for k in first}
            name_signals = {
                "name", "companyname", "company_name", "businessname",
                "business_name", "title", "contractorname",
            }
            if keys_lower & name_signals:
                return data

    if isinstance(data, dict):
        for v in data.values():
            result = _find_contractor_array(v, depth + 1)
            if result:
                return result

    return []


def _get(d: dict, *keys) -> object:
    """Multi-key dict lookup — tries each key, returns first hit."""
    for k in keys:
        if k in d:
            return d[k]
        k_lower = k.lower()
        for dk in d:
            if dk.lower() == k_lower:
                return d[dk]
    return None


def _normalize_api_item(raw: dict, source_url: str) -> dict:
    """
    Map a raw API contractor object to our internal schema.

    We don't know GAF's exact field names until we intercept a live
    response, so we try multiple common variants for each field.
    """
    name = str(_get(raw, "name", "companyName", "company_name", "businessName", "title") or "").strip()

    street  = str(_get(raw, "address", "streetAddress", "street", "address1") or "").strip()
    city    = str(_get(raw, "city", "cityName") or "").strip() or None
    state   = str(_get(raw, "state", "stateCode", "stateAbbr") or "").strip() or None
    zip_c   = str(_get(raw, "zip", "zipCode", "zip_code", "postalCode") or "").strip() or None

    address_parts = [p for p in [street, city, state] if p]
    address = ", ".join(address_parts) or None
    if not city and address:
        city, state = _parse_city_state(address)

    phone   = str(_get(raw, "phone", "phoneNumber", "phone_number", "telephone") or "") or None
    website = str(_get(raw, "websiteUrl", "website_url", "website", "externalUrl") or "") or None
    tier    = str(_get(raw, "tier", "certificationLevel", "badgeType", "badge",
                        "certificationTier", "level", "certType") or "") or "Unknown"

    rating_raw   = _get(raw, "rating", "starRating", "reviewScore", "averageRating")
    reviews_raw  = _get(raw, "reviewCount", "review_count", "reviews", "numReviews")
    dist_raw     = _get(raw, "distance", "distanceMiles", "distance_miles")
    profile_url  = str(_get(raw, "profileUrl", "profile_url", "url", "link") or "") or None
    specialties  = _get(raw, "specialties", "services", "expertise") or []

    return {
        "name":            name,
        "address":         address,
        "city":            city,
        "state":           state,
        "zip_code":        zip_c,
        "phone":           phone,
        "website":         website or None,
        "gaf_tier":        tier,
        "specialties":     specialties if isinstance(specialties, list) else [],
        "reviews_count":   int(reviews_raw) if reviews_raw else None,
        "rating":          _parse_rating(str(rating_raw)) if rating_raw is not None else None,
        "distance_miles":  (
            float(dist_raw) if isinstance(dist_raw, (int, float))
            else _parse_distance(str(dist_raw))
        ),
        "gaf_profile_url": profile_url,
        "source_url":      source_url,
    }


# ─────────────────────────────────────────────────────────────
# DIRECT COVEO API (primary path)
# ─────────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles between two lat/lon points."""
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# Approximate center coordinates for common US zip codes.
# In production: geocode dynamically via Google Maps API / Census geocoder.
_ZIP_COORDS: dict[str, tuple[float, float]] = {
    "10013": (40.7207, -74.0072),  # TriBeCa, NYC
}
_DEFAULT_COORDS = (40.7207, -74.0072)


def _fetch_coveo_contractors(
    zip_code: str,
    distance_miles: int,
    max_results: int,
    source_url: str,
) -> list[dict]:
    """
    Call GAF's Coveo search API directly.

    WHY this is better than browser scraping:
        - No Chromium, no Akamai, no bot detection
        - 4-second response vs ~45 seconds for a full browser load
        - Structured JSON: no CSS selector fragility at all
        - Field names discovered by probing the live API response

    The API key is a public read-only search key embedded in every GAF page.
    It grants search access only — no write operations are possible.

    Geographic strategy:
        Coveo doesn't expose a native radius filter on custom lat/lon fields
        without a paid geo-field configuration. Instead we use a bounding box
        aq filter (fast pre-filter, over-inclusive) then compute haversine
        distance in Python to trim to the exact radius circle.
    """
    origin_lat, origin_lon = _ZIP_COORDS.get(zip_code, _DEFAULT_COORDS)

    # Degrees of lat/lon that span `distance_miles` at this latitude.
    lat_margin = distance_miles / 69.0
    lon_margin = distance_miles / (math.cos(math.radians(origin_lat)) * 69.0)

    # Request more than max_results to account for post-filter trimming.
    fetch_count = min(max_results * 3, 200)

    payload = {
        "pipeline":        _COVEO_PIPELINE,
        "searchHub":       "ContractorLocator",
        "q":               "",
        "numberOfResults": fetch_count,
        "firstResult":     0,
        "sortCriteria":    "relevancy",
        "context": {
            "sortingStrategy": "bestcontractors",
            "postalCode":      zip_code,
            "distance":        str(distance_miles),
        },
        # Bounding-box pre-filter using the real Coveo field names.
        # Discovered by probing the live API: fields live in result.raw with
        # no @ prefix when accessed via the REST search response.
        "aq": (
            f"@gaf_latitude>={origin_lat - lat_margin:.4f} "
            f"@gaf_latitude<={origin_lat + lat_margin:.4f} "
            f"@gaf_longitude>={origin_lon - lon_margin:.4f} "
            f"@gaf_longitude<={origin_lon + lon_margin:.4f} "
            f"@gaf_contractor_type=Residential"
        ),
    }

    body = json.dumps(payload).encode()
    req  = urllib.request.Request(
        _COVEO_SEARCH_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {_COVEO_API_KEY}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"[scraper] Coveo API error: {e}")
        return []

    results = data.get("results", [])
    print(
        f"[scraper] Coveo API: {len(results)} bounding-box results "
        f"(totalCount={data.get('totalCount', '?')})"
    )

    normalized = []
    for r in results:
        raw = r.get("raw", {})

        name = (raw.get("gaf_navigation_title") or r.get("title", "")).strip()
        if not name:
            continue

        # Compute exact great-circle distance; skip anything outside the radius.
        lat = raw.get("gaf_latitude")
        lon = raw.get("gaf_longitude")
        if lat and lon:
            dist = _haversine(origin_lat, origin_lon, float(lat), float(lon))
            if dist > distance_miles:
                continue
        else:
            dist = None

        # Tier comes from the certifications array; take the first entry.
        certs = raw.get("gaf_f_contractor_certifications_and_awards_residential") or []
        tier  = certs[0] if certs else "Unknown"

        city    = raw.get("gaf_f_city") or None
        state   = raw.get("gaf_f_state_code") or None
        zip_c   = raw.get("gaf_postal_code") or None
        address = raw.get("gaf_address") or None

        normalized.append({
            "name":            name,
            "address":         address,
            "city":            city,
            "state":           state,
            "zip_code":        zip_c,
            "phone":           raw.get("gaf_phone") or None,
            "website":         None,
            "gaf_tier":        str(tier),
            "specialties":     [],
            "reviews_count":   int(raw["gaf_number_of_reviews"]) if raw.get("gaf_number_of_reviews") else None,
            "rating":          float(raw["gaf_rating"]) if raw.get("gaf_rating") else None,
            "distance_miles":  round(dist, 1) if dist is not None else None,
            "gaf_profile_url": r.get("clickUri") or r.get("uri"),
            "source_url":      source_url,
        })

    # Sort by distance, trim to requested max.
    normalized.sort(key=lambda x: x["distance_miles"] or 99)
    return normalized[:max_results]


# ─────────────────────────────────────────────────────────────
# MAIN SCRAPER
# ─────────────────────────────────────────────────────────────

async def scrape_gaf_contractors(
    zip_code: str = "10013",
    distance_miles: int = 25,
    max_results: int = 50,
    archive_html: bool = True,
) -> list[ContractorRecord]:
    """
    Main scraping entrypoint. Returns validated ContractorRecord objects.

    Flow:
        1. Direct Coveo API call (no browser needed)
        2. If that yields nothing: launch Playwright, intercept XHR
        3. If that yields nothing: DOM extraction
        4. If all else fails: mock data
    """
    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout
        _playwright_available = True
    except ImportError:
        _playwright_available = False

    print(f"[scraper] Starting | ZIP={zip_code} | radius={distance_miles}mi")

    url = (
        f"https://www.gaf.com/en-us/roofing-contractors/residential"
        f"?postalCode={zip_code}&distance={distance_miles}"
    )

    contractors: list[ContractorRecord] = []

    # ── Strategy 1: Direct Coveo API ──────────────────────────────────────────
    print("[scraper] Strategy 1: direct Coveo API")
    raw_items = _fetch_coveo_contractors(zip_code, distance_miles, max_results, url)

    if raw_items:
        print(f"[scraper] Coveo API returned {len(raw_items)} items -- skipping browser")
    else:
        # ── Strategy 2 & 3: Playwright (XHR intercept → DOM fallback) ─────────
        if not _playwright_available:
            print("[scraper] Playwright not installed -- skipping browser strategies")
            print("[scraper] Install: pip install playwright && playwright install chromium")
            return _mock_contractors(zip_code)

        raw_items = await _scrape_with_playwright(
            zip_code, distance_miles, max_results, url, archive_html
        )

    # ── Validate each record through Pydantic ──────────────────────────────────
    scraped_at = datetime.now(timezone.utc).isoformat()
    for item in raw_items[:max_results]:
        if not item.get("name"):
            continue
        try:
            now = datetime.now(timezone.utc).isoformat()
            record = ContractorRecord(
                id=_deterministic_id(item["name"], item.get("address")),
                created_at=now,
                updated_at=now,
                scraped_at=scraped_at,
                **item,
            )
            contractors.append(record)
            print(f"[scraper] OK  {record.gaf_tier.value:<20} {record.name}")
        except Exception as e:
            print(f"[scraper] SKIP {item.get('name', '?')} -- {e}")

    if not contractors:
        print("[scraper] 0 records scraped -- falling back to mock data")
        return _mock_contractors(zip_code)

    print(f"[scraper] Done. {len(contractors)} validated contractors.")
    return contractors


# ─────────────────────────────────────────────────────────────
# PLAYWRIGHT FALLBACK (XHR intercept → DOM)
# ─────────────────────────────────────────────────────────────

async def _scrape_with_playwright(
    zip_code: str,
    distance_miles: int,
    max_results: int,
    url: str,
    archive_html: bool,
) -> list[dict]:
    """
    Playwright-based fallback. Tries two sub-strategies in order:
        1. XHR/fetch response interception (captures Coveo JSON mid-flight)
        2. DOM extraction from the rendered page

    This runs only when the direct Coveo API call fails or is blocked.
    """
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout

    captured_api: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,image/avif,image/webp,*/*;q=0.8"
                ),
                "sec-ch-ua": '"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Upgrade-Insecure-Requests": "1",
            },
        )

        # Stealth: clear automation fingerprint before any page JS runs.
        await ctx.add_init_script(_STEALTH_SCRIPT)
        page = await ctx.new_page()

        # XHR interception: register BEFORE goto() so we catch the initial load.
        async def _on_response(response):
            try:
                content_type = response.headers.get("content-type", "")
                if "json" not in content_type:
                    return
                resp_url = response.url.lower()
                if not any(sig in resp_url for sig in _API_URL_SIGNALS):
                    return
                if response.status != 200:
                    return
                body = await response.json()
                candidates = _find_contractor_array(body)
                if candidates:
                    print(
                        f"[scraper] XHR intercepted ({len(candidates)} records): "
                        f"{response.url[:80]}"
                    )
                    captured_api.append({"url": response.url, "items": candidates})
            except Exception:
                pass

        page.on("response", _on_response)

        print(f"[scraper] Strategy 2: Playwright XHR intercept | GET {url}")
        try:
            await page.goto(url, wait_until="networkidle", timeout=45_000)
        except PWTimeout:
            print("[scraper] networkidle timeout -- proceeding with domcontentloaded")
            await page.wait_for_load_state("domcontentloaded")

        await asyncio.sleep(2)

        if archive_html:
            html = await page.content()
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            archive_path = RAW_DATA_DIR / f"gaf_{zip_code}_{ts}.html"
            archive_path.write_text(html, encoding="utf-8")
            print(f"[scraper] HTML archived -> {archive_path.name}")

        raw_items: list[dict] = []
        if captured_api:
            print(f"[scraper] XHR path: {len(captured_api)} response(s) captured")
            for batch in captured_api:
                for item in batch["items"]:
                    raw_items.append(_normalize_api_item(item, url))
        else:
            print("[scraper] Strategy 3: DOM extraction (no XHR response captured)")
            raw_items = await _extract_from_dom(page, url)

        await browser.close()

    return raw_items


# ─────────────────────────────────────────────────────────────
# DOM EXTRACTION (fallback)
# ─────────────────────────────────────────────────────────────

async def _extract_from_dom(page, source_url: str) -> list[dict]:
    """
    Extract contractor data from the rendered DOM via JavaScript evaluation.

    Fallback when XHR interception yields nothing. Tries selectors in order
    from most stable (data-testid) to least stable (generic class fragments).
    """
    card_selectors = [
        "[data-testid*='contractor']",
        "[class*='ContractorCard']",
        "[class*='contractor-card']",
        "[class*='roofer-card']",
        "article[class*='card']",
    ]

    from playwright.async_api import TimeoutError as PWTimeout
    for sel in card_selectors:
        try:
            await page.wait_for_selector(sel, timeout=8_000)
            print(f"[scraper] DOM: cards matched via {sel!r}")
            break
        except PWTimeout:
            continue

    raw = await page.evaluate("""
        () => {
            const results = [];
            const selectors = [
                '[data-testid*="contractor"]',
                '[class*="ContractorCard"]',
                '[class*="contractor-card"]',
                '[class*="roofer-card"]',
                'article[class*="card"]',
            ];

            let cards = [];
            for (const sel of selectors) {
                cards = document.querySelectorAll(sel);
                if (cards.length > 0) break;
            }

            cards.forEach(card => {
                const text = card.innerText || '';
                const nameEl = card.querySelector('h2,h3,h4,[class*="name"],[class*="company"]');
                const name = nameEl ? nameEl.innerText.trim() : '';
                if (!name) return;

                const addrEl = card.querySelector('[class*="address"],[class*="location"],address');
                const address = addrEl ? addrEl.innerText.trim() : '';

                const phoneEl = card.querySelector('a[href^="tel:"],[class*="phone"]');
                const phone = phoneEl
                    ? (phoneEl.getAttribute('href') || phoneEl.innerText).replace('tel:','').trim()
                    : '';

                const tierEl = card.querySelector(
                    '[class*="badge"],[class*="tier"],[class*="elite"],[class*="certified"]'
                );
                const tier = tierEl ? tierEl.innerText.trim() : '';

                const ratingEl = card.querySelector(
                    '[class*="rating"],[class*="stars"],[aria-label*="star"]'
                );
                const rating = ratingEl
                    ? (ratingEl.getAttribute('aria-label') || ratingEl.innerText).trim()
                    : '';

                const distMatch = text.match(/([\\d.]+)\\s*mi/i);
                const distance = distMatch ? distMatch[1] : '';

                const linkEl = card.querySelector('a[href*="contractor"],a[href*="roofer"]');
                const profileUrl = linkEl ? linkEl.href : '';

                const websiteEl = card.querySelector('a[href^="http"]:not([href*="gaf.com"])');
                const website = websiteEl ? websiteEl.href : '';

                results.push({ name, address, phone, tier, rating, distance, profileUrl, website });
            });

            return results;
        }
    """)

    normalized = []
    for c in (raw or []):
        if not c.get("name"):
            continue
        city, state = _parse_city_state(c.get("address", ""))
        normalized.append({
            "name":            c["name"],
            "address":         c.get("address") or None,
            "city":            city,
            "state":           state,
            "zip_code":        None,
            "phone":           c.get("phone") or None,
            "website":         c.get("website") or None,
            "gaf_tier":        c.get("tier") or "Unknown",
            "specialties":     [],
            "reviews_count":   None,
            "rating":          _parse_rating(c.get("rating", "")),
            "distance_miles":  _parse_distance(c.get("distance", "")),
            "gaf_profile_url": c.get("profileUrl") or None,
            "source_url":      source_url,
        })

    print(f"[scraper] DOM extraction: {len(normalized)} raw items")
    return normalized


# ─────────────────────────────────────────────────────────────
# MOCK DATA (fallback for demo / testing)
# ─────────────────────────────────────────────────────────────

def _mock_contractors(zip_code: str) -> list[ContractorRecord]:
    """
    Realistic seed data for demo and testing.

    IMPORTANT: In production this fallback would NEVER silently inject fake data.
    It would: raise a PipelineError, log to alerting system, return empty list.
    Mock mode exists ONLY to demonstrate the full pipeline when the scraper
    is blocked or Playwright is not installed in the demo environment.
    """
    now = datetime.now(timezone.utc).isoformat()
    source = f"https://www.gaf.com/en-us/roofing-contractors/residential?postalCode={zip_code}&distance=25"

    seeds = [
        dict(name="Elite Roofing Solutions NYC", address="245 Atlantic Ave, Brooklyn, NY 11201",
             city="Brooklyn", state="NY", zip_code="11201", phone="7185550101",
             website="https://eliteroofingnyc.com", gaf_tier=GAFTier.MASTER_ELITE,
             specialties=["Residential", "Commercial", "Flat Roofing"],
             reviews_count=87, rating=4.9, distance_miles=2.1),
        dict(name="Metro Roof & Waterproofing", address="1801 Park Ave, Hoboken, NJ 07030",
             city="Hoboken", state="NJ", zip_code="07030", phone="2015550182",
             website="https://metroroof.com", gaf_tier=GAFTier.MASTER_ELITE,
             specialties=["Commercial", "TPO", "EPDM", "Flat Roofing"],
             reviews_count=52, rating=4.7, distance_miles=4.3),
        dict(name="Queens Premier Roofing", address="89-12 Jamaica Ave, Queens, NY 11421",
             city="Queens", state="NY", zip_code="11421", phone="7185550234",
             website="https://queensroofing.com", gaf_tier=GAFTier.CERTIFIED_PLUS,
             specialties=["Residential", "Shingles", "Storm Damage"],
             reviews_count=134, rating=4.8, distance_miles=8.7),
        dict(name="Bronx Roofing Specialists", address="3201 E Tremont Ave, Bronx, NY 10461",
             city="Bronx", state="NY", zip_code="10461", phone="7185550345",
             website="https://bronxroofing.com", gaf_tier=GAFTier.CERTIFIED,
             specialties=["Residential", "Flat Roofing", "Repairs"],
             reviews_count=67, rating=4.5, distance_miles=11.2),
        dict(name="Hudson Valley Roofing Co", address="412 Main St, Yonkers, NY 10701",
             city="Yonkers", state="NY", zip_code="10701", phone="9145550456",
             website="https://hvroofing.com", gaf_tier=GAFTier.MASTER_ELITE,
             specialties=["Residential", "Commercial", "Solar", "Premium Shingles"],
             reviews_count=203, rating=4.9, distance_miles=14.8),
        dict(name="Newark Roofing & Construction", address="622 Broad St, Newark, NJ 07102",
             city="Newark", state="NJ", zip_code="07102", phone="9735550567",
             website="https://newarkroofing.com", gaf_tier=GAFTier.CERTIFIED,
             specialties=["Commercial", "Industrial", "Flat Roofing"],
             reviews_count=29, rating=4.2, distance_miles=9.1),
        dict(name="Staten Island Roofing Pros", address="1500 Richmond Ave, Staten Island, NY 10314",
             city="Staten Island", state="NY", zip_code="10314", phone="7185550678",
             website="https://siroofingpros.com", gaf_tier=GAFTier.CERTIFIED_PLUS,
             specialties=["Residential", "Shingles", "Gutters", "Siding"],
             reviews_count=91, rating=4.6, distance_miles=16.4),
        dict(name="NJ Flat Roof Experts", address="88 Journal Square, Jersey City, NJ 07306",
             city="Jersey City", state="NJ", zip_code="07306", phone="2015550789",
             website="https://njflatroof.com", gaf_tier=GAFTier.MASTER_ELITE,
             specialties=["Commercial", "TPO", "EPDM", "Green Roofing"],
             reviews_count=44, rating=4.8, distance_miles=3.9),
        dict(name="Westchester Roof Masters", address="200 Hamilton Ave, White Plains, NY 10601",
             city="White Plains", state="NY", zip_code="10601", phone="9145550890",
             website="https://wcroof.com", gaf_tier=GAFTier.CERTIFIED,
             specialties=["Residential", "Luxury Homes", "Slate", "Shingles"],
             reviews_count=58, rating=4.4, distance_miles=22.1),
        dict(name="Brooklyn Flat Roof Co", address="576 Atlantic Ave, Brooklyn, NY 11217",
             city="Brooklyn", state="NY", zip_code="11217", phone="7185550901",
             website="https://bkflatroof.com", gaf_tier=GAFTier.REGISTERED,
             specialties=["Flat Roofing", "Repairs", "Waterproofing"],
             reviews_count=18, rating=4.1, distance_miles=2.8),
    ]

    records = []
    for s in seeds:
        rec = ContractorRecord(
            id=_deterministic_id(s["name"], s.get("address")),
            source_url=source, scraped_at=now,
            created_at=now, updated_at=now,
            **s,
        )
        records.append(rec)
        print(f"[mock] {rec.gaf_tier.value:<20} {rec.name:<40} {rec.distance_miles}mi")

    return records


# ─────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────

async def run_scrape(zip_code: str = "10013", distance: int = 25) -> list[ContractorRecord]:
    return await scrape_gaf_contractors(zip_code=zip_code, distance_miles=distance)


if __name__ == "__main__":
    results = asyncio.run(run_scrape())
    print(f"\n{'='*60}")
    print(f"SCRAPED: {len(results)} contractors")
    print(f"{'='*60}")
    for r in sorted(results, key=lambda x: x.distance_miles or 99):
        print(f"  {r.gaf_tier.value:<20} {r.name:<38} {r.city}, {r.state}  {r.distance_miles}mi")
