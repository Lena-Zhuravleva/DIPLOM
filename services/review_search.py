import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    )
}


def clean_text(value):
    if not value:
        return ""

    return re.sub(r"\s+", " ", value).strip()


def extract_review_blocks(html):
    soup = BeautifulSoup(html, "html.parser")

    reviews = []

    selectors = [
        ".review",
        ".comment",
        ".item",
        "article",
        "p"
    ]

    for selector in selectors:
        elements = soup.select(selector)

        for el in elements:
            text = clean_text(el.get_text(" ", strip=True))

            if len(text) < 50:
                continue

            if len(text) > 800:
                text = text[:800]

            if text not in reviews:
                reviews.append(text)

            if len(reviews) >= 10:
                return reviews

    return reviews


def search_reviews_by_company(company_name):
    """
    Пробует получить отзывы о компании
    через открытые страницы поиска.
    """

    if not company_name:
        return {
            "success": False,
            "error": "Название компании не указано",
            "reviews": []
        }

    search_urls = [
        f"https://otzovik.com/?search_text={quote(company_name)}",
        f"https://irecommend.ru/search/content/{quote(company_name)}"
    ]

    all_reviews = []

    for url in search_urls:

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=15
            )

            if response.status_code >= 400:
                continue

            reviews = extract_review_blocks(response.text)

            for r in reviews:
                if r not in all_reviews:
                    all_reviews.append(r)

        except Exception:
            continue

    if not all_reviews:
        return {
            "success": False,
            "error": "Отзывы не найдены",
            "reviews": []
        }

    return {
        "success": True,
        "reviews": all_reviews[:10],
        "text": "\n".join(all_reviews[:10])
    }