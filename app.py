from flask import Flask, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
import os
import hashlib
from datetime import datetime, timezone
import re

app = Flask(__name__)

DATABASE_FILE = "programs.DB"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
    )
}

SOURCES = {
    "ABC": [
        "https://www.abc.net.au/tv",
        "https://help.abc.net.au/hc/en-us/articles/11774354457871-Latest-program-announcements"
    ],
    "SBS": [
    "https://www.sbs.com.au/whats-on",
    "https://www.sbs.com.au/whats-on/collection/tv-shows",
    "https://www.sbs.com.au/whats-on/article/top-new-tv-series-to-watch-this-september-2026/pqhttdrab"
],
    "10": [
        "https://10.com.au/"
    ]
}

# Words that usually indicate this is NOT a TV program
IGNORE_WORDS = [
    "about", "contact", "careers", "privacy", "terms",
    "accessibility", "login", "sign-in", "subscribe",
    "facebook", "instagram", "youtube", "twitter",
    "sport", "sports", "news", "weather",
    "movie", "movies", "trailer", "trailers",
    "article", "articles", "collection", "collections",
    "video", "videos", "podcast", "podcasts",
    "competition", "competitions",
    "advertisement", "skip-advertisement",
    "stream-now", "watch-live"
]

# Titles that are clearly website navigation rather than programs
IGNORE_TITLES = [
    "home",
    "search",
    "menu",
    "login",
    "sign in",
    "about us",
    "contact us",
    "careers",
    "privacy",
    "terms",
    "accessibility",
    "stream now",
    "stream free",
    "watch now",
    "watch live",
    "skip advertisement",
    "subscribe",
    "more",
    "learn more",
    "read more",
    "view all",
    "see all",
    "announcement",
    "interview",
    "collection",
    "viewing guide",
    "what to watch"

]


def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def clean_program_title(network, title, url=""):
    title = clean_text(title)

    if network == "SBS":
        # SBS program URLs contain the clean program slug
        match = re.search(r"/tv-series/([^/?#]+)", url.lower())

        if match:
            slug = match.group(1)

            # Turn "party-down" into "Party Down"
            return slug.replace("-", " ").title()

    return title
    
def load_programs():
    if not os.path.exists(DATA_FILE):
        return []

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return []


def save_programs(programs):
    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(
            programs,
            file,
            indent=2,
            ensure_ascii=False
        )


def make_id(network, url, title):
    value = network + "|" + url + "|" + title
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def fetch_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


def looks_like_program(network, title, url):
    title_lower = title.lower()
    url_lower = url.lower()

    # Reject obvious navigation/content
    if title_lower in IGNORE_TITLES:
        return False

    if any(word in title_lower for word in [
        "skip advertisement",
        "stream now",
        "watch live"
    ]):
        return False

    # Reject obvious non-program URLs
    bad_url_parts = [
        "/article/",
        "/articles/",
        "/news/",
        "/sport/",
        "/sports/",
        "/video/",
        "/videos/",
        "/trailer/",
        "/trailers/",
        "/collection/",
        "/collections/",
        "/podcast/",
        "/podcasts/",
        "/search",
        "/login",
        "/about",
        "/contact",
        "/careers",
        "/privacy",
        "/terms"
    ]

    if any(part in url_lower for part in bad_url_parts):
        return False

           # ABC
    if network == "ABC":
        if "abc.net.au" not in url_lower:
            return False

        # Ignore ABC TV guide and navigation pages
        if any(part in url_lower for part in [
            "/tv/",
            "/tv/epg",
            "/tv/guide",
            "/tv/classification",
            "/tv/watchoutfor"
        ]):
            return False

        # Keep only actual ABC iview program pages
        if "iview.abc.net.au/show/" not in url_lower:
            return False

        # Ignore iview collections and general pages
        if any(part in url_lower for part in [
            "/collection/",
            "/shows"
        ]):
            return False

    # SBS
    elif network == "SBS":
        if "sbs.com.au" not in url_lower:
            return False

        if not any(part in url_lower for part in [
            "/ondemand/tv-series/",
            "/whats-on/"
        ]):
            return False

    # Network 10
    elif network == "10":
        if "10.com.au" not in url_lower:
            return False

        # Keep only links that look like program/content pages
        if url_lower.rstrip("/") == "https://10.com.au":
            return False

    return True


def get_description(link):
    # Try nearby HTML first
    parent = link.parent

    if parent:
        text = clean_text(
            parent.get_text(" ", strip=True)
        )

        if text and text != clean_text(
            link.get_text(" ", strip=True)
        ):
            return text

    # Try the surrounding container
    container = link.find_parent(
        ["article", "li", "section", "div"]
    )

    if container:
        text = clean_text(
            container.get_text(" ", strip=True)
        )

        title = clean_text(
            link.get_text(" ", strip=True)
        )

        if text != title and len(text) > len(title):
            return text

    return ""


def scrape_source(network, url):
    soup = fetch_page(url)
    results = []

    for link in soup.find_all("a", href=True):

        href = urljoin(
            url,
            link["href"]
        )

        raw_title = clean_text(
            link.get_text(" ", strip=True)
        )

        title = clean_program_title(
            network,
            raw_title,
            href
        )

        if len(title) < 3 or len(title) > 150:
            continue
        href = urljoin(
            url,
            link["href"]
        )

        if not looks_like_program(
            network,
            title,
            href
        ):
            continue

        description = get_description(link)

        if len(description) > 700:
            description = description[:700] + "..."

        results.append({
            "network": network,
            "title": title,
            "description": description,
            "url": href
        })

        return results


def scrape_sbs_announcement(url):
    soup = fetch_page(url)
    results = []

    for heading in soup.find_all(["h2", "h3"]):

        title = clean_text(
            heading.get_text(" ", strip=True)
        )

        if not title:
            continue

        # Ignore website navigation and article headings
        if title.lower() in [
            "stream now on demand",
            "follow sbs",
            "download our apps",
            "listen to our podcasts",
            "watch sbs on demand",
            "explore sbs",
            "languages",
            "contact sbs"
        ]:
            continue

        if title.lower().startswith(
            "series coming to sbs"
        ):
            continue

        if len(title) > 120:
            continue

        description_parts = []

        for element in heading.find_all_next():

            if element.name in ["h2", "h3"]:
                break

            text = clean_text(
                element.get_text(" ", strip=True)
            )

            if text:
                description_parts.append(text)

            if len(description_parts) >= 3:
                break

        description = " ".join(
            description_parts
        )

        # Ignore short program-card metadata
        if (
            len(description) < 100
            or description.lower().startswith("series •")
        ):
            continue

        results.append({
            "network": "SBS",
            "title": title,
            "description": description,
            "url": url
        })

    return results


def scrape_all():
    existing = load_programs()

    known_ids = {
        item.get("id")
        for item in existing
    }

    new_items = []

    for network, urls in SOURCES.items():

        for url in urls:

            try:
                if (
                    network == "SBS"
                    and "top-new-tv-series" in url
                ):
                    items = scrape_sbs_announcement(url)
                else:
                    items = scrape_source(
                        network,
                        url
                    )
               
                for item in items:

                    item_id = make_id(
                        item["network"],
                        item["url"],
                        item["title"]
                    )

                    if item_id in known_ids:
                        continue

                    item["id"] = item_id

                    item["first_seen"] = (
                        datetime.now(
                            timezone.utc
                        ).isoformat()
                    )

                    item["new"] = True

                    existing.append(item)

                    known_ids.add(item_id)

                    new_items.append(item)

            except Exception as error:

                print(
                    f"{network} error: {error}"
                )

    save_programs(existing)

    return new_items


@app.route("/")
def home():
    return """
    <h1>Australian TV Watcher</h1>

    <p>The scraper is running.</p>

    <p>
        <a href="/api/scan">
            Run a scan
        </a>
    </p>

    <p>
        <a href="/api/programs">
            View saved programs
        </a>
    </p>
    """


@app.route("/api/test-sbs")
def test_sbs():
    url = "https://www.sbs.com.au/whats-on/article/top-new-tv-series-to-watch-this-september-2026/pqhttdrab"

    results = scrape_sbs_announcement(url)

    return jsonify(results)

    new_items = scrape_all()

    return jsonify({
        "new_programs": new_items,
        "count": len(new_items)
    })

@app.route("/api/reset")
def reset():
    save_programs([])

    return jsonify({
        "status": "reset",
        "message": "All saved programs have been cleared."
    })
@app.route("/api/programs")
def programs():

    data = load_programs()

    data.sort(
        key=lambda item: item.get(
            "first_seen",
            ""
        ),
        reverse=True
    )

    return jsonify(data)


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        )
    )
    
@app.route("/api/scan")
def scan():
    new_items = scrape_all()

    return jsonify({
        "new_programs": new_items,
        "count": len(new_items)
    })
