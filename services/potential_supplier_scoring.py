from models import SupplierMaterial, Material
from services.supplier_scoring import (
    normalize_cost,
    calculate_ahp_weights,
    get_ahp_matrix_by_scenario,
    calculate_nonlinear_score
)


def score_potential_supplier(
    material_query,
    price,
    lead_time_days,
    rating,
    review_risk_score=None,
    scenario='balanced'
):
    material = None

    if material_query:
        material = Material.query.filter(
            Material.name.ilike(f'%{material_query}%')
        ).first()

    prices = []
    lead_times = []

    if material:
        rows = SupplierMaterial.query.filter_by(
            material_id=material.id,
            is_active=True
        ).all()

        prices = [float(r.price) for r in rows if r.price is not None]
        lead_times = [
            int(r.lead_time_days)
            for r in rows
            if r.lead_time_days is not None
        ]

    price = float(price) if price not in [None, ''] else None
    lead_time_days = int(lead_time_days) if lead_time_days not in [None, ''] else None
    rating = float(rating) if rating not in [None, ''] else 3.0

    if price is not None:
        prices.append(price)

    if lead_time_days is not None:
        lead_times.append(lead_time_days)

    # Базовые диапазоны для новых поставщиков,
    # если по материалу мало данных в текущей базе
    if len(prices) < 2:
        min_price = price * 0.7 if price else None
        max_price = price * 1.5 if price else None
    else:
        min_price = min(prices)
        max_price = max(prices)

    # Для срока поставки задаём понятную шкалу:
    # 1 день = отлично, 30 дней = плохо
    if len(lead_times) < 2:
        min_lead = 1
        max_lead = 30
    else:
        min_lead = min(lead_times)
        max_lead = max(lead_times)

    ahp_matrix = get_ahp_matrix_by_scenario(scenario)
    ahp_weights = calculate_ahp_weights(ahp_matrix)

    weights = {
        "rating": 0.20,
        "price": 0.25,
        "lead_time": 0.25,
        "reliability": 0.15,
        "risk": 0.15,
    }

    rating_score = max(0, min(1, rating / 5))

    price_score = (
        normalize_cost(price, min_price, max_price)
        if price is not None
        else 0.5
    )

    lead_time_score = (
        normalize_cost(lead_time_days, min_lead, max_lead)
        if lead_time_days is not None
        else 0.5
    )

    if review_risk_score is not None and float(review_risk_score) <= 0.25 and rating >= 4.0:
        reliability_score = 0.75
    elif review_risk_score is not None and float(review_risk_score) <= 0.45 and rating >= 3.5:
        reliability_score = 0.65
    else:
        reliability_score = 0.5

    if review_risk_score is None:
        risk_score = 0.5
    else:
        risk_score = max(0, min(1, float(review_risk_score)))

    hybrid_score = calculate_nonlinear_score(
        rating_score=rating_score,
        price_score=price_score,
        lead_time_score=lead_time_score,
        reliability_score=reliability_score,
        risk_score=risk_score,
        weights=weights
    )

    warnings = []

    if price_score < 0.4:
        warnings.append("Цена поставщика выше средней по категории.")

    if lead_time_score < 0.4:
        warnings.append("Срок поставки значительно превышает рекомендуемый.")

    if risk_score > 0.6:
        warnings.append("Обнаружен высокий риск по результатам анализа отзывов.")

    if rating_score < 0.5:
        warnings.append("Рейтинг поставщика ниже среднего.")

    if reliability_score < 0.6:
        warnings.append("Надежность поставщика пока недостаточно подтверждена историей поставок.")

    return {
        "rating_score": round(rating_score, 3),
        "price_score": round(price_score, 3),
        "lead_time_score": round(lead_time_score, 3),
        "reliability_score": round(reliability_score, 3),
        "risk_score": round(risk_score, 3),
        "hybrid_score": hybrid_score,
        "weights": weights,
        "warnings": warnings
    }
