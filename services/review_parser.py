import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


BASE_URL = "https://for-driver.info"
CATALOG_URL = "https://for-driver.info/review-company"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    )
}


def normalize_text(value):
    return (value or "").strip().lower()


def find_company_on_for_driver(company_query, max_pages=5):
    query = normalize_text(company_query)

    if not query:
        return None

    for page in range(1, max_pages + 1):
        url = CATALOG_URL if page == 1 else f"{CATALOG_URL}?page={page}"

        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        company_links = soup.select('a[href*="/review-company/"]')

        for link in company_links:
            name = link.get_text(" ", strip=True)

            if not name:
                continue

            low_name = normalize_text(name)

            if query in low_name or low_name in query:
                href = link.get("href")
                review_url = urljoin(BASE_URL, href)

                card = link.find_parent()
                address = ""

                if card:
                    card_text = card.get_text(" ", strip=True)
                    address = card_text.replace(name, "").strip()

                return {
                    "company_name": name,
                    "address": address,
                    "review_url": review_url
                }

    return None


def parse_reviews_from_company_name(company_query, limit=5):
    company = find_company_on_for_driver(company_query)

    if not company:
        return {
            "success": False,
            "error": "Компания не найдена в каталоге отзывов.",
            "company_name": company_query,
            "address": "",
            "reviews": []
        }

    response = requests.get(company["review_url"], headers=HEADERS, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    reviews = []

    selectors = [
        ".review",
        ".comment",
        ".testimonial",
        "article",
        "p"
    ]

    for selector in selectors:
        elements = soup.select(selector)

        for el in elements:
            text = el.get_text(" ", strip=True)

            if not text:
                continue

            if len(text) < 40:
                continue

            if len(text) > 700:
                text = text[:700]

            if text not in reviews:
                reviews.append(text)

            if len(reviews) >= limit:
                break

        if len(reviews) >= limit:
            break

    if not reviews:
        return {
            "success": False,
            "error": "Компания найдена, но отзывы не удалось извлечь.",
            "company_name": company["company_name"],
            "address": company["address"],
            "review_url": company["review_url"],
            "reviews": []
        }

    return {
        "success": True,
        "company_name": company["company_name"],
        "address": company["address"],
        "review_url": company["review_url"],
        "reviews": reviews,
        "text": "\n".join(reviews)
    }