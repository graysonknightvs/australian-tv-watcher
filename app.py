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
DATA_FILE = "programs.json"
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
        "https://www.sbs.com.au/whats-on"
    ],
    "10": [
        "https://10.com.au/"
    ]
}
IGNORE_WORDS = [
    "login",
    "sign-in",
    "privacy",
    "terms",
    "contact",
    "facebook",
    "instagram",
    "youtube",
    "twitter",
    "search",
    "subscribe",
    "accessibility"
]
def clean_text(text):
    if not text:
        return ""
    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()
def load_programs():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(
            DATA_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)
    except Exception:
        return []
def save_programs(programs):
    with open(
        DATA_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            programs,
            file,
            indent=2,
            ensure_ascii=False
        )
def make_id(network, url, title):
    value = (
        network
        + "|"
        + url
        + "|"
        + title
    )
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
def scrape_source(network, url):
    soup = fetch_page(url)
    results = []
    for link in soup.find_all(
        "a",
        href=True
    ):
        title = clean_text(
            link.get_text(
                " ",
                strip=True
            )
        )
        if not title:
            continue
        if len(title) < 3:
            continue
        if len(title) > 150:
            continue
        href = urljoin(
            url,
            link["href"]
        )
        lower_url = href.lower()
        if any(
            word in lower_url
            for word in IGNORE_WORDS
        ):
            continue
        # Make sure the link belongs to the broadcaster.
        if network == "ABC":
            if "abc.net.au" not in lower_url:
                continue
        elif network == "SBS":
            if "sbs.com.au" not in lower_url:
                continue
        elif network == "10":
            if "10.com.au" not in lower_url:
                continue
        # Try to find a useful description near the link.
        description = ""
        parent = link.parent
        if parent:
            description = clean_text(
                parent.get_text(
                    " ",
                    strip=True
                )
            )
        # Don't let the title simply become
        # a gigantic duplicate description.
        if description == title:
            description = ""
        if len(description) > 700:
            description = (
                description[:700]
                + "..."
            )
        results.append({
            "network": network,
            "title": title,
            "description": description,
            "url": href
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
                    item["id"] = item_id
                    if item_id in known_ids:
                        continue
                    item["first_seen"] = (
                        datetime.now(
                            timezone.utc
                        ).isoformat()
                    )
                    item["new"] = True
                    existing.append(item)
                    known_ids.add(
                        item_id
                    )
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
@app.route("/api/scan")
def scan():
    new_items = scrape_all()
    return jsonify({
        "new_programs": new_items,
        "count": len(new_items)
    })
@app.route("/api/programs")
def programs():
    data = load_programs()
    data.sort(
        key=lambda item:
        item.get(
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
