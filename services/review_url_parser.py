import re
import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    )
}


BAD_WORDS = [
    "copyright",
    "личный кабинет",
    "корзина",
    "каталог",
    "доставка и оплата",
    "доставка и оплата",
    "политика конфиденциальности",
    "оставьте ваше сообщение",
    "специалисты свяжутся",
    "посмотреть на карте",
    "подписаться",
    "обратный звонок",
    "оформить заказ",
    "согласен на обработку",
    "общий рейтинг магазина",
    "оставить отзыв",
    "правила публикации",
    "авторизованные пользователи",
    "отзыв полезен",
    "закрыть окно",
    "обратная связь",
    "вход регистрация",
    "выберите ваш город",
    "доставка отзывы блог контакты",
    "есть вопросы",
]


REVIEW_MARKERS = [
    "отзыв",
    "купил",
    "купила",
    "заказ",
    "заказывал",
    "заказывала",
    "достав",
    "получил",
    "получила",
    "товар",
    "качество",
    "цена",
    "срок",
    "быстро",
    "долго",
    "менеджер",
    "рекомендую",
    "понравилось",
    "не понравилось",
    "хорошо",
    "плохо",
    "проблем",
    "задерж",
    "брака",
    "магазин",
]


def clean_text(value):
    if not value:
        return ""

    value = re.sub(r"\s+", " ", value)
    return value.strip()

def clean_review_noise(text):
    patterns = [
        r"Общий рейтинг магазина",
        r"Отзывов:\s*\d+",
        r"Оставить отзыв",
        r"Вы можете оценить качество работы нашего магазина.*?сайте",
        r"Отзыв полезен\?\s*Да\s*\(\s*\d+\s*\)\s*Нет\s*\(\s*\d+\s*\)",
        r"Закрыть окно.*",
        r"Есть вопросы\?.*",
    ]

    result = text

    for pattern in patterns:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)

    return clean_text(result)

def is_review_like(text):
    if not text:
        return False

    low = text.lower()

    if len(text) < 80:
        return False

    if len(text) > 1500:
        return False

    if any(word in low for word in BAD_WORDS):
        return False

    marker_count = sum(1 for marker in REVIEW_MARKERS if marker in low)

    return marker_count >= 2


def extract_reviews_from_soup(soup, limit=15):
    reviews = []

    selectors = [
        '[class*="review"]',
        '[class*="comment"]',
        '[class*="feedback"]',
        '[class*="testimonial"]',
        '[class*="opinion"]',
        '[itemprop="review"]',
        "article",
        "blockquote",
    ]

    for selector in selectors:
        for el in soup.select(selector):
            text = clean_text(el.get_text(" ", strip=True))
            text = clean_review_noise(text)

            if is_review_like(text):
                clean_short = text[:250]

                already_exists = any(
                    clean_short in r or r[:250] in clean_short
                    for r in reviews
                )

                if not already_exists:
                    reviews.append(text[:1200])

            if len(reviews) >= limit:
                return reviews

    # fallback: если классы не нашли, смотрим абзацы
    for el in soup.select("p, div"):
        text = clean_text(el.get_text(" ", strip=True))
        text = clean_review_noise(text)

        if is_review_like(text):
            clean_short = text[:250]

            already_exists = any(
                clean_short in r or r[:250] in clean_short
                for r in reviews
            )

            if not already_exists:
                reviews.append(text[:1200])

        if len(reviews) >= limit:
            return reviews

    return reviews


def parse_reviews_from_url(url, limit=15):
    response = requests.get(url, headers=HEADERS, timeout=20)

    if response.status_code >= 400:
        return {
            "success": False,
            "error": f"Страница отзывов не загрузилась. Код: {response.status_code}",
            "reviews": []
        }

    soup = BeautifulSoup(response.text, "html.parser")

    # Убираем очевидные служебные блоки
    for tag in soup.select("script, style, nav, header, footer, form, aside"):
        tag.decompose()

    reviews = extract_reviews_from_soup(soup, limit=limit)

    if not reviews:
        return {
            "success": False,
            "error": "Отзывы не найдены: страница открылась, но подходящих текстов отзывов не обнаружено.",
            "reviews": []
        }

    return {
        "success": True,
        "reviews": reviews,
        "text": "\n\n".join(reviews)
    }