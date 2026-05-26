import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


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


def extract_price(text):
    if not text:
        return None

    patterns = [
        r"([0-9]{1,3}(?:[\s][0-9]{3})*(?:[,.][0-9]{1,2})?)\s*(₽|руб|р\.)",
        r"Цена[:\s]*([0-9]{1,3}(?:[\s][0-9]{3})*(?:[,.][0-9]{1,2})?)",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)

        for match in matches:

            if isinstance(match, tuple):
                raw = match[0]
            else:
                raw = match

            raw = raw.replace(" ", "").replace(",", ".")

            # слишком длинные числа — вероятно артикулы
            if len(raw.split(".")[0]) > 6:
                continue

            try:
                value = float(raw)

                # фильтр мусора
                if value < 10 or value > 1000000:
                    continue

                return value

            except ValueError:
                continue

    return None


def guess_supplier_name(domain):
    if not domain:
        return ""

    domain = domain.replace("www.", "")

    known = {
        "intercom-nn.ru": "Интерком-НН",
        "intercom.su": "Интерком-НН",
        "texbalt.ru": "Техбалт",
        "holod-magazin.ru": "Холод-Магазин",
        "holodon.ru": "Холодон",
        "cool-centre.ru": "Эйркул",
        "optlist.ru": "Поставщик с OptList",
    }

    return known.get(domain, domain)


def parse_external_offer(url):
    """
    Универсальный парсер коммерческого предложения.

    Работает с обычными HTML-страницами:
    - intercom-nn.ru
    - intercom.su
    - texbalt.ru
    - holod-magazin.ru
    - holodon.ru
    - optlist.ru

    Если сайт не отдаёт HTML, возвращает ошибку.
    """

    response = requests.get(url, headers=HEADERS, timeout=20)

    if response.status_code >= 400:
        return {
            "success": False,
            "error": f"Сайт не отдал страницу. Код ответа: {response.status_code}"
        }

    soup = BeautifulSoup(response.text, "html.parser")

    page_text = clean_text(soup.get_text(" ", strip=True))

    title = ""

    h1 = soup.select_one("h1")
    if h1:
        title = clean_text(h1.get_text(" ", strip=True))

    if not title and soup.title:
        title = clean_text(soup.title.get_text(" ", strip=True))

    price = extract_price(page_text)

    domain = urlparse(url).netloc.lower()
    supplier_name = guess_supplier_name(domain)

    city = ""

    possible_cities = [
        "Москва", "Санкт-Петербург", "Нижний Новгород", "Воронеж",
        "Липецк", "Курск", "Белгород", "Тула", "Рязань",
        "Смоленск", "Тверь", "Екатеринбург", "Новосибирск", "Казань"
    ]

    for city_name in possible_cities:
        if city_name.lower() in page_text.lower():
            city = city_name
            break

    category = "Холодильные комплектующие"

    if "компрессор" in page_text.lower():
        category = "Холодильные компрессоры"
    elif "уплотн" in page_text.lower():
        category = "Уплотнители"
    elif "плата" in page_text.lower():
        category = "Электронные компоненты"
    elif "ручк" in page_text.lower():
        category = "Комплектующие корпуса"

    return {
        "success": True,
        "company_name": supplier_name,
        "material_query": title,
        "price": price,
        "city": city,
        "category": category,
        "source_url": url
    }