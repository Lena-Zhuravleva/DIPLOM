from models import SupplierMaterial, Material
from services.supplier_scoring import (
    normalize_cost,
    calculate_supply_cost,
    calculate_nonlinear_score,
    get_ahp_matrix_by_scenario,
    calculate_ahp_weights
)


def build_weights_by_scenario(scenario):
    ahp_matrix = get_ahp_matrix_by_scenario(scenario)
    ahp_weights = calculate_ahp_weights(ahp_matrix)

    return {
        "rating": ahp_weights[0],
        "price": ahp_weights[1],
        "lead_time": ahp_weights[2],
        "quality": ahp_weights[3],
        "reliability": ahp_weights[4],
        "risk": ahp_weights[5],
    }


def score_potential_supplier(
        material_query,
        price,
        lead_time_days,
        rating,
        delivery_cost=0,
        incoterms='EXW',
        review_risk_score=None,
        scenario='balanced',
        # ===== ДОБАВИТЬ ЭТОТ ПАРАМЕТР =====
        quality_score=None  # 1-5 или None
):
    material = None

    if material_query:
        material = Material.query.filter(
            Material.name.ilike(f'%{material_query}%')
        ).first()

    supply_costs = []
    lead_times = []

    if material:
        rows = SupplierMaterial.query.filter_by(
            material_id=material.id,
            is_active=True
        ).all()

        supply_costs = [
            calculate_supply_cost(r.price, r.delivery_cost, r.incoterms)
            for r in rows
            if r.price is not None
        ]

        lead_times = [
            int(r.lead_time_days)
            for r in rows
            if r.lead_time_days is not None
        ]

    price = float(price) if price not in [None, ''] else None
    delivery_cost = float(delivery_cost) if delivery_cost not in [None, ''] else 0
    incoterms = incoterms or 'EXW'
    lead_time_days = int(lead_time_days) if lead_time_days not in [None, ''] else None
    rating = float(rating) if rating not in [None, ''] else 3.0

    supply_cost = calculate_supply_cost(price, delivery_cost, incoterms) if price is not None else None

    if supply_cost is not None:
        supply_costs.append(supply_cost)

    if lead_time_days is not None:
        lead_times.append(lead_time_days)

    if len(supply_costs) < 2:
        min_price = supply_cost * 0.7 if supply_cost else None
        max_price = supply_cost * 1.5 if supply_cost else None
    else:
        min_price = min(supply_costs)
        max_price = max(supply_costs)

    if len(lead_times) < 2:
        min_lead = 1
        max_lead = 30
    else:
        min_lead = min(lead_times)
        max_lead = max(lead_times)

    weights = build_weights_by_scenario(scenario)

    rating_score = max(0, min(1, rating / 5))

    price_score = (
        normalize_cost(supply_cost, min_price, max_price)
        if supply_cost is not None
        else 0.5
    )

    lead_time_score = (
        normalize_cost(lead_time_days, min_lead, max_lead)
        if lead_time_days is not None
        else 0.5
    )

    # ============================================================
    # ===== ИЗМЕНЕНИЕ: РАСЧЕТ quality_score =====
    # ============================================================

    quality_warning = None

    if quality_score is not None:
        try:
            q_val = float(quality_score)
            if 1 <= q_val <= 5:
                quality_score_norm = q_val / 5  # нормализуем в [0, 1]
                if q_val >= 4:
                    quality_warning = f"✅ Качество подтверждено (оценка {q_val}/5)"
                elif q_val >= 3:
                    quality_warning = f"⚠️ Качество удовлетворительное ({q_val}/5)"
                else:
                    quality_warning = f"❌ Качество низкое ({q_val}/5)"
            else:
                quality_score_norm = 0.5
                quality_warning = "⚠️ Некорректная оценка качества, используется нейтральное значение"
        except (ValueError, TypeError):
            quality_score_norm = 0.5
            quality_warning = "⚠️ Некорректная оценка качества, используется нейтральное значение"
    else:
        # Не указана оценка качества — используем нейтральное значение
        quality_score_norm = 0.5
        quality_warning = "⚠️ Качество не проверено"

    # ============================================================

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

    # ===== ИСПОЛЬЗУЕМ quality_score_norm ВМЕСТО СТАРОГО quality_score = 0.7 =====

    hybrid_score = calculate_nonlinear_score(
        rating_score=rating_score,
        price_score=price_score,
        lead_time_score=lead_time_score,
        quality_score=quality_score_norm,  # <-- ИЗМЕНЕНО
        reliability_score=reliability_score,
        risk_score=risk_score,
        weights=weights
    )

    warnings = []

    if price_score < 0.4:
        warnings.append("Стоимость поставки выше средней по категории.")

    if lead_time_score < 0.4:
        warnings.append("Срок поставки значительно превышает рекомендуемый.")

    if risk_score > 0.6:
        warnings.append("Обнаружен высокий риск по результатам анализа отзывов.")

    if rating_score < 0.5:
        warnings.append("Рейтинг поставщика ниже среднего.")

    if reliability_score < 0.6:
        warnings.append("Надежность поставщика пока недостаточно подтверждена историей поставок.")

    # ===== ДОБАВЛЯЕМ ПРЕДУПРЕЖДЕНИЕ О КАЧЕСТВЕ =====
    if quality_warning:
        warnings.append(quality_warning)

    return {
        "rating_score": round(rating_score, 3),
        "price_score": round(price_score, 3),
        "lead_time_score": round(lead_time_score, 3),
        "quality_score": round(quality_score_norm, 3),  # нормализованная [0,1]
        "quality_score_raw": quality_score,  # исходная 1-5 или None
        "quality_checked": quality_score is not None,  # True/False
        "reliability_score": round(reliability_score, 3),
        "risk_score": round(risk_score, 3),
        "hybrid_score": hybrid_score,
        "weights": {
            "rating": round(weights["rating"], 3),
            "price": round(weights["price"], 3),
            "lead_time": round(weights["lead_time"], 3),
            "quality": round(weights["quality"], 3),
            "reliability": round(weights["reliability"], 3),
            "risk": round(weights["risk"], 3),
        },
        "warnings": warnings,
        "supply_cost": round(supply_cost, 2) if supply_cost is not None else None,
        "material_price": round(price, 2) if price is not None else None,
        "delivery_cost": round(delivery_cost, 2),
        "incoterms": incoterms
    }