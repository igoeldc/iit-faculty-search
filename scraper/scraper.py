"""
Illinois Tech Faculty Scraper
=============================
Two-phase scraper:
  Phase 1 - Crawl /directory/people (paginated) to collect all faculty profile URLs.
  Phase 2 - Scrape each individual profile page for full details.

Output: faculty.json  (list of faculty dicts)
"""

import json
import re
import time
import sys
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.iit.edu"
DIRECTORY_URL = f"{BASE_URL}/directory/people"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; IIT-Faculty-Scraper/1.0; "
        "academic research project)"
    )
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_soup(url: str, params: dict = None, retries: int = 3) -> BeautifulSoup | None:
    """Fetch a URL and return a BeautifulSoup object, with simple retry logic."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as exc:
            print(f"  [warn] attempt {attempt+1}/{retries} failed for {url}: {exc}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


def clean(text: str) -> str:
    """Strip and collapse whitespace."""
    return re.sub(r"\s+", " ", text).strip() if text else ""


# ---------------------------------------------------------------------------
# Phase 1: Collect profile URLs from the directory listing
# ---------------------------------------------------------------------------

def scrape_directory(faculty_only: bool = True, max_pages: int = 100) -> list[str]:
    """
    Paginate through /directory/people and collect profile hrefs.
    Returns a deduplicated list of absolute profile URLs.
    """
    profile_urls: list[str] = []
    seen: set[str] = set()
    page = 0

    # Filter params: profile_type=21 = Faculty
    base_params = {"profile_type": 21} if faculty_only else {}

    print("=== Phase 1: Collecting profile URLs ===")
    while page < max_pages:
        params = {**base_params, "page": page} if page > 0 else base_params
        print(f"  Fetching directory page {page} …", end=" ", flush=True)
        soup = get_soup(DIRECTORY_URL, params=params)
        if soup is None:
            print("FAILED – stopping pagination.")
            break

        # Profile cards: <article> or <div> with a link to /directory/people/<slug>
        links = soup.select("a[href*='/directory/people/']")
        new_on_page = 0
        for a in links:
            href = a.get("href", "")
            # Skip the listing page itself and filter/sort links
            if href.count("/") < 3:
                continue
            abs_url = urljoin(BASE_URL, href.split("?")[0])
            if abs_url not in seen and abs_url != DIRECTORY_URL:
                seen.add(abs_url)
                profile_urls.append(abs_url)
                new_on_page += 1

        print(f"found {new_on_page} new profiles (total: {len(profile_urls)})")

        # Detect last page: no "next" pager link
        next_link = soup.select_one("a[rel='next'], li.pager__item--next a")
        if not next_link:
            print("  No next page – done paginating.")
            break
        page += 1
        time.sleep(0.5)   # be polite

    return profile_urls


# ---------------------------------------------------------------------------
# Phase 2: Scrape individual profile pages
# ---------------------------------------------------------------------------

def parse_list_section(heading_tag) -> list[str]:
    """
    Given a heading tag (h2/h3), collect all <li> text under the next <ul>.
    """
    items = []
    sib = heading_tag.find_next_sibling()
    while sib:
        if sib.name in ("h2", "h3", "h4"):
            break
        if sib.name == "ul":
            items.extend(clean(li.get_text()) for li in sib.find_all("li"))
        sib = sib.find_next_sibling()
    return items


def scrape_profile(url: str) -> dict | None:
    """Scrape a single faculty profile page and return a structured dict."""
    soup = get_soup(url)
    if soup is None:
        return None

    data: dict = {"profile_url": url}

    # --- Name ---
    h1 = soup.find("h1")
    data["name"] = clean(h1.get_text()) if h1 else ""

    # --- Title / Role ---
    # IIT profile pages use <div class="hero__positions"> for the faculty title
    positions_div = soup.find("div", class_="hero__positions")
    if positions_div:
        titles = [clean(p.get_text()) for p in positions_div.find_all("p")]
        if not titles:
            titles = [clean(positions_div.get_text())]
    else:
        titles = []
    data["titles"] = [t for t in titles if t]

    # --- Department & profile-type tags ---
    # IIT uses <div class="listing-item__tags tags"> with two <ul>s:
    #   first ul = profile type (Faculty/Staff/etc.)
    #   subsequent ul(s) = department/college links
    tags_div = soup.find("div", class_="listing-item__tags")
    profile_types = []
    departments = []
    if tags_div:
        uls = tags_div.find_all("ul")
        for i, ul in enumerate(uls):
            for a in ul.find_all("a"):
                href = a.get("href", "")
                text = clean(a.get_text())
                if not text:
                    continue
                if "profile_type" in href or i == 0:
                    profile_types.append(text)
                else:
                    departments.append(text)
    data["profile_types"] = profile_types
    data["departments"] = departments

    # --- Contact ---
    email_tag = soup.find("a", href=re.compile(r"^mailto:"))
    data["email"] = email_tag["href"].replace("mailto:", "").strip() if email_tag else ""

    phone_tag = soup.find("a", href=re.compile(r"^tel:"))
    data["phone"] = clean(phone_tag.get_text()) if phone_tag else ""

    # --- Structured sections (Education, Research Interests, etc.) ---
    section_map = {
        "education": [],
        "research_interests": [],
        "professional_affiliations": [],
        "publications": [],
        "books": [],
        "patents": [],
    }

    SECTION_KEYS = {
        "education": "education",
        "research interests": "research_interests",
        "research areas": "research_interests",
        "professional affiliations": "professional_affiliations",
        "memberships": "professional_affiliations",
        "publications": "publications",
        "books": "books",
        "patents": "patents",
    }

    for heading in soup.find_all(["h2", "h3", "h4"]):
        heading_text = clean(heading.get_text()).lower()
        for keyword, key in SECTION_KEYS.items():
            if keyword in heading_text:
                items = parse_list_section(heading)
                # Also grab plain paragraphs (some sections use <p> not <ul>)
                if not items:
                    sib = heading.find_next_sibling()
                    while sib and sib.name not in ("h2", "h3", "h4"):
                        if sib.name == "p":
                            t = clean(sib.get_text())
                            if t:
                                items.append(t)
                        sib = sib.find_next_sibling()
                section_map[key].extend(items)
                break

    data.update(section_map)

    # --- Google Scholar link ---
    scholar = soup.find("a", href=re.compile(r"scholar\.google\.com"))
    data["google_scholar_url"] = scholar["href"] if scholar else ""

    # --- Profile photo ---
    img = soup.find("img", src=re.compile(r"/sites/default/files"))
    data["photo_url"] = urljoin(BASE_URL, img["src"]) if img else ""

    return data


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    output_path = "faculty.json"

    # ---- Phase 1 ----
    profile_urls = scrape_directory(faculty_only=True)
    if not profile_urls:
        print("No profile URLs found – check if the directory structure changed.")
        sys.exit(1)

    print(f"\nCollected {len(profile_urls)} profile URLs.\n")

    # ---- Phase 2 ----
    print("=== Phase 2: Scraping individual profiles ===")
    faculty: list[dict] = []
    for i, url in enumerate(profile_urls, 1):
        print(f"  [{i}/{len(profile_urls)}] {url}")
        profile = scrape_profile(url)
        if profile:
            faculty.append(profile)
        time.sleep(0.4)   # polite delay

    # ---- Save ----
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(faculty, f, indent=2, ensure_ascii=False)

    print(f"\nDone! Saved {len(faculty)} faculty records to '{output_path}'.")


if __name__ == "__main__":
    main()