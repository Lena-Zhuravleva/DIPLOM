from models import SupplierMaterial, Delivery
from services.ml_training import predict_supplier_risk


def get_incoterms_coefficient(incoterms):
    coeffs = {
        'EXW': 1.0,
        'FCA': 0.8,
        'FOB': 0.5,
        'CIF': 0.2,
        'DAP': 0.1,
        'DDP': 0.0
    }
    return coeffs.get(incoterms or 'EXW', 1.0)


def calculate_supply_cost(price, delivery_cost, incoterms):
    return float(price or 0) + float(delivery_cost or 0) * get_incoterms_coefficient(incoterms)


def calculate_ahp_weights(matrix):
    n = len(matrix)
    geo_means = []

    for row in matrix:
        product = 1
        for value in row:
            product *= value
        geo_means.append(product ** (1 / n))

    total = sum(geo_means)

    if total == 0:
        return [1 / n] * n

    return [gm / total for gm in geo_means]


def get_ahp_matrix_by_scenario(scenario):
    """
    Порядок критериев:
    0 - рейтинг
    1 - стоимость поставки
    2 - срок
    3 - качество
    4 - надежность
    5 - риск
    """

    matrices = {
        "balanced": [
            [1,   2,   2,   1,   1,   3],
            [1/2, 1,   2,   1/2, 1/2, 2],
            [1/2, 1/2, 1,   1/2, 1/2, 2],
            [1,   2,   2,   1,   1,   3],
            [1,   2,   2,   1,   1,   3],
            [1/3, 1/2, 1/2, 1/3, 1/3, 1],
        ],

        "low_cost": [
            [1,   1/3, 1,   1/2, 1/2, 2],
            [3,   1,   3,   2,   2,   4],
            [1,   1/3, 1,   1/2, 1/2, 2],
            [2,   1/2, 2,   1,   1,   3],
            [2,   1/2, 2,   1,   1,   3],
            [1/2, 1/4, 1/2, 1/3, 1/3, 1],
        ],

        "fast_delivery": [
            [1,   1,   1/3, 1/2, 1/2, 2],
            [1,   1,   1/3, 1/2, 1/2, 2],
            [3,   3,   1,   2,   2,   4],
            [2,   2,   1/2, 1,   1,   3],
            [2,   2,   1/2, 1,   1,   3],
            [1/2, 1/2, 1/4, 1/3, 1/3, 1],
        ],

        "reliable": [
            [1,   2,   2,   1/2, 1/2, 1/2],
            [1/2, 1,   1,   1/3, 1/3, 1/3],
            [1/2, 1,   1,   1/3, 1/3, 1/3],
            [2,   3,   3,   1,   1/2, 2],
            [2,   3,   3,   2,   1,   2],
            [2,   3,   3,   1/2, 1/2, 1],
        ],
    }

    return matrices.get(scenario, matrices["balanced"])


def normalize_cost(value, min_value, max_value):
    if value is None or min_value is None or max_value is None:
        return 0.5

    if max_value == min_value:
        return 0.5

    score = 1 - ((value - min_value) / (max_value - min_value))
    return max(0, min(1, score))


def calculate_supplier_reliability(supplier_id):
    total_deliveries = Delivery.query.filter_by(supplier_id=supplier_id).count()

    completed_deliveries = Delivery.query.filter_by(
        supplier_id=supplier_id,
        status='delivered'
    ).count()

    reliability_score = completed_deliveries / total_deliveries if total_deliveries > 0 else 0.5

    return {
        "total_deliveries": total_deliveries,
        "completed_deliveries": completed_deliveries,
        "reliability_score": max(0, min(1, reliability_score))
    }


def calculate_supplier_quality(supplier_id):
    rows = Delivery.query.filter(
        Delivery.supplier_id == supplier_id,
        Delivery.status == 'delivered',
        Delivery.quality_score.isnot(None)
    ).all()

    if not rows:
        return {
            "avg_quality": 5,
            "quality_score": 1.0
        }

    avg_quality = sum(d.quality_score for d in rows) / len(rows)

    return {
        "avg_quality": round(avg_quality, 2),
        "quality_score": max(0, min(1, avg_quality / 5))
    }


def calculate_supplier_risk(supplier_id, total_deliveries):
    delivered_rows = Delivery.query.filter(
        Delivery.supplier_id == supplier_id,
        Delivery.status == 'delivered',
        Delivery.delay_minutes.isnot(None)
    ).all()

    avg_delay = sum(d.delay_minutes for d in delivered_rows) / len(delivered_rows) if delivered_rows else 0

    bad_quality_count = Delivery.query.filter(
        Delivery.supplier_id == supplier_id,
        Delivery.status == 'delivered',
        Delivery.quality_score.isnot(None),
        Delivery.quality_score <= 2
    ).count()

    if avg_delay > 120:
        delay_risk = 1.0
    elif avg_delay > 60:
        delay_risk = 0.7
    elif avg_delay > 30:
        delay_risk = 0.4
    else:
        delay_risk = 0.1

    quality_risk = bad_quality_count / total_deliveries if total_deliveries > 0 else 0.0

    risk_score = min(1.0, (delay_risk * 0.7) + (quality_risk * 0.3))

    return {
        "risk_score": risk_score,
        "avg_delay": avg_delay,
        "bad_quality_count": bad_quality_count
    }


def build_reasons(price_score, rating_score, lead_time_score, quality_score, reliability_score, risk_score):
    reasons = []

    if price_score > 0.8:
        reasons.append('выгодная стоимость поставки')

    if rating_score > 0.8:
        reasons.append('высокий рейтинг')

    if lead_time_score > 0.8:
        reasons.append('короткий срок поставки')

    if quality_score > 0.8:
        reasons.append('высокое качество продукции')

    if reliability_score > 0.7:
        reasons.append('надёжный поставщик')

    if risk_score > 0.5:
        reasons.append('есть риск задержек или проблем с качеством')

    if risk_score <= 0.2:
        reasons.append('низкий риск')

    if not reasons:
        reasons.append('сбалансированные показатели')

    return reasons


def calculate_nonlinear_score(
    rating_score,
    price_score,
    lead_time_score,
    quality_score,
    reliability_score,
    risk_score,
    weights
):
    risk_component = 1 - risk_score

    rating_component = max(rating_score, 0.01)
    price_component = max(price_score, 0.01)
    lead_component = max(lead_time_score, 0.01)
    quality_component = max(quality_score, 0.01)
    reliability_component = max(reliability_score, 0.01)
    risk_component = max(risk_component, 0.01)

    nonlinear_score = (
        (rating_component ** weights["rating"]) *
        (price_component ** weights["price"]) *
        (lead_component ** weights["lead_time"]) *
        (quality_component ** weights["quality"]) *
        (reliability_component ** weights["reliability"]) *
        (risk_component ** weights["risk"])
    )

    return round(nonlinear_score * 100, 2)


def calculate_topsis_scores(raw_candidates, weights):
    if not raw_candidates:
        return {}

    criteria = [
        "rating_score",
        "price_score",
        "lead_time_score",
        "quality_score",
        "reliability_score",
        "risk_component"
    ]

    criteria_weights = {
        "rating_score": weights["rating"],
        "price_score": weights["price"],
        "lead_time_score": weights["lead_time"],
        "quality_score": weights["quality"],
        "reliability_score": weights["reliability"],
        "risk_component": weights["risk"],
    }

    denominators = {}

    for c in criteria:
        denominators[c] = sum((item[c] ** 2 for item in raw_candidates)) ** 0.5
        if denominators[c] == 0:
            denominators[c] = 1

    normalized = []

    for item in raw_candidates:
        row = {"supplier_id": item["supplier_id"]}

        for c in criteria:
            row[c] = (item[c] / denominators[c]) * criteria_weights[c]

        normalized.append(row)

    ideal = {}
    anti_ideal = {}

    for c in criteria:
        values = [row[c] for row in normalized]
        ideal[c] = max(values)
        anti_ideal[c] = min(values)

    result = {}

    for row in normalized:
        d_plus = sum((row[c] - ideal[c]) ** 2 for c in criteria) ** 0.5
        d_minus = sum((row[c] - anti_ideal[c]) ** 2 for c in criteria) ** 0.5

        closeness = d_minus / (d_plus + d_minus) if d_plus + d_minus != 0 else 0
        result[row["supplier_id"]] = round(closeness * 100, 2)

    return result


def score_suppliers_for_material(material_id, scenario="balanced"):
    rows = SupplierMaterial.query.filter_by(
        material_id=material_id,
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

    min_price = min(supply_costs) if supply_costs else None
    max_price = max(supply_costs) if supply_costs else None

    min_lead = min(lead_times) if lead_times else None
    max_lead = max(lead_times) if lead_times else None

    ahp_matrix = get_ahp_matrix_by_scenario(scenario)
    ahp_weights = calculate_ahp_weights(ahp_matrix)

    weights = {
        "rating": ahp_weights[0],
        "price": ahp_weights[1],
        "lead_time": ahp_weights[2],
        "quality": ahp_weights[3],
        "reliability": ahp_weights[4],
        "risk": ahp_weights[5],
    }

    candidates = []
    raw_candidates_for_topsis = []

    for relation in rows:
        supplier = relation.supplier

        if not supplier or not supplier.is_active:
            continue

        rating = float(supplier.rating or 0)
        material_price = float(relation.price) if relation.price is not None else None
        delivery_cost = float(relation.delivery_cost or 0)
        incoterms = relation.incoterms or 'EXW'

        supply_cost = calculate_supply_cost(
            material_price,
            delivery_cost,
            incoterms
        ) if material_price is not None else None

        lead_time = int(relation.lead_time_days) if relation.lead_time_days is not None else None

        rating_score = max(0, min(1, rating / 5))
        price_score = normalize_cost(supply_cost, min_price, max_price)
        lead_time_score = normalize_cost(lead_time, min_lead, max_lead)

        quality_data = calculate_supplier_quality(supplier.id)
        avg_quality = quality_data["avg_quality"]
        quality_score = quality_data["quality_score"]

        reliability_data = calculate_supplier_reliability(supplier.id)
        total_deliveries = reliability_data["total_deliveries"]
        completed_deliveries = reliability_data["completed_deliveries"]
        reliability_score = reliability_data["reliability_score"]

        risk_data = calculate_supplier_risk(supplier.id, total_deliveries)
        risk_score = risk_data["risk_score"]
        avg_delay = risk_data["avg_delay"]
        bad_quality_count = risk_data["bad_quality_count"]

        ml_risk_probability = predict_supplier_risk({
            "price": supply_cost or 0,
            "lead_time_days": lead_time or 0,
            "supplier_rating": rating or 0,
            "quantity": 0,
            "duration_min": 0,
            "delay_minutes": avg_delay or 0,
            "quality_score": avg_quality or 5
        })

        if ml_risk_probability is not None:
            scoring_risk_score = round((0.6 * risk_score) + (0.4 * ml_risk_probability), 3)
        else:
            scoring_risk_score = risk_score

        ml_risk_percent = round(100 * ml_risk_probability, 1) if ml_risk_probability is not None else None
        q_score = calculate_nonlinear_score(
            rating_score=rating_score,
            price_score=price_score,
            lead_time_score=lead_time_score,
            quality_score=quality_score,
            reliability_score=reliability_score,
            risk_score=risk_score,
            weights=weights
        ) / 100
        s_score = 1 - scoring_risk_score

        alpha = 0.7

        final_score = round((alpha * q_score + (1 - alpha) * s_score) * 100, 2)

        reasons = build_reasons(
            price_score=price_score,
            rating_score=rating_score,
            lead_time_score=lead_time_score,
            quality_score=quality_score,
            reliability_score=reliability_score,
            risk_score=scoring_risk_score
        )

        risk_component = max(1 - scoring_risk_score, 0.01)

        raw_candidates_for_topsis.append({
            "supplier_id": supplier.id,
            "rating_score": rating_score,
            "price_score": price_score,
            "lead_time_score": lead_time_score,
            "quality_score": quality_score,
            "reliability_score": reliability_score,
            "risk_component": risk_component
        })

        candidates.append({
            'supplier_id': supplier.id,
            'supplier': supplier.company_name,

            'rating': rating,

            'material_price': round(material_price, 2) if material_price is not None else None,
            'delivery_cost': round(delivery_cost, 2),
            'incoterms': incoterms,
            'incoterms_coefficient': get_incoterms_coefficient(incoterms),
            'price': round(supply_cost, 2) if supply_cost is not None else None,
            'supply_cost': round(supply_cost, 2) if supply_cost is not None else None,

            'lead_time_days': lead_time,
            'avg_quality': avg_quality,

            'mcdm_score': round(q_score * 100, 2),
            'scoring_score': round(s_score * 100, 2),
            'alpha': alpha,

            'score': final_score,

            'rating_score': round(rating_score, 3),
            'price_score': round(price_score, 3),
            'lead_time_score': round(lead_time_score, 3),
            'quality_score': round(quality_score, 3),
            'reliability_score': round(reliability_score, 3),
            'risk_score': round(scoring_risk_score, 3),
            'rule_risk_score': round(risk_score, 3),
            'ml_risk_probability': ml_risk_probability,
            'ml_risk_percent': ml_risk_percent,

            'avg_delay': round(avg_delay, 1),
            'bad_quality_count': bad_quality_count,
            'total_deliveries': total_deliveries,
            'completed_deliveries': completed_deliveries,

            'reasons': reasons,
            'model_type': 'ahp_nonlinear_dynamic_risk_ml_scoring',

            'topsis_score': None
        })

    topsis_scores = calculate_topsis_scores(raw_candidates_for_topsis, weights)

    for item in candidates:
        item["topsis_score"] = topsis_scores.get(item["supplier_id"])

    candidates.sort(key=lambda x: x['score'], reverse=True)

    return {
        "scenario": scenario,
        "weights": {
            "rating": round(weights["rating"], 3),
            "price": round(weights["price"], 3),
            "lead_time": round(weights["lead_time"], 3),
            "quality": round(weights["quality"], 3),
            "reliability": round(weights["reliability"], 3),
            "risk": round(weights["risk"], 3),
        },
        "items": candidates
    }