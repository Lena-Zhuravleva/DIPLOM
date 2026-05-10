from models import SupplierMaterial, Delivery
from services.ml_training import predict_supplier_risk

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
    1 - цена
    2 - срок
    3 - надежность
    4 - риск
    """

    matrices = {
        "balanced": [
            [1,   2,   2,   1,   3],
            [1/2, 1,   2,   1/2, 2],
            [1/2, 1/2, 1,   1/2, 2],
            [1,   2,   2,   1,   3],
            [1/3, 1/2, 1/2, 1/3, 1],
        ],

        "low_cost": [
            [1,   1/3, 1,   1/2, 2],
            [3,   1,   3,   2,   4],
            [1,   1/3, 1,   1/2, 2],
            [2,   1/2, 2,   1,   3],
            [1/2, 1/4, 1/2, 1/3, 1],
        ],

        "fast_delivery": [
            [1,   1,   1/3, 1/2, 2],
            [1,   1,   1/3, 1/2, 2],
            [3,   3,   1,   2,   4],
            [2,   2,   1/2, 1,   3],
            [1/2, 1/2, 1/4, 1/3, 1],
        ],

        "reliable": [
            [1,   2,   2,   1/2, 1/2],
            [1/2, 1,   1,   1/3, 1/3],
            [1/2, 1,   1,   1/3, 1/3],
            [2,   3,   3,   1,   2],
            [2,   3,   3,   1/2, 1],
        ],
    }

    return matrices.get(scenario, matrices["balanced"])


def normalize_cost(value, min_value, max_value):
    """
    Для затратных критериев:
    меньше значение = лучше.
    Например цена или срок.
    """
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

    if total_deliveries > 0:
        reliability_score = completed_deliveries / total_deliveries
    else:
        reliability_score = 0.5

    return {
        "total_deliveries": total_deliveries,
        "completed_deliveries": completed_deliveries,
        "reliability_score": max(0, min(1, reliability_score))
    }


def calculate_supplier_risk(supplier_id, total_deliveries):
    delivered_rows = Delivery.query.filter(
        Delivery.supplier_id == supplier_id,
        Delivery.status == 'delivered',
        Delivery.delay_minutes.isnot(None)
    ).all()

    if delivered_rows:
        avg_delay = sum(d.delay_minutes for d in delivered_rows) / len(delivered_rows)
    else:
        avg_delay = 0

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

    if total_deliveries > 0:
        quality_risk = bad_quality_count / total_deliveries
    else:
        quality_risk = 0.0

    risk_score = min(1.0, (delay_risk * 0.7) + (quality_risk * 0.3))

    return {
        "risk_score": risk_score,
        "avg_delay": avg_delay,
        "bad_quality_count": bad_quality_count
    }


def build_reasons(price_score, rating_score, lead_time_score, reliability_score, risk_score):
    reasons = []

    if price_score > 0.8:
        reasons.append('выгодная цена')

    if rating_score > 0.8:
        reasons.append('высокий рейтинг')

    if lead_time_score > 0.8:
        reasons.append('короткий срок поставки')

    if reliability_score > 0.7:
        reasons.append('надёжный поставщик')

    if risk_score > 0.5:
        reasons.append('есть риск задержек')

    if risk_score <= 0.2:
        reasons.append('низкий риск')

    if not reasons:
        reasons.append('сбалансированные показатели')

    return reasons


def calculate_nonlinear_score(
    rating_score,
    price_score,
    lead_time_score,
    reliability_score,
    risk_score,
    weights
):
    """
    Нелинейная свёртка:
    score = Π(x_i ^ w_i)

    Риск превращаем в положительный критерий:
    меньше риск = лучше, поэтому risk_component = 1 - risk_score.
    """

    risk_component = 1 - risk_score

    rating_component = max(rating_score, 0.01)
    price_component = max(price_score, 0.01)
    lead_component = max(lead_time_score, 0.01)
    reliability_component = max(reliability_score, 0.01)
    risk_component = max(risk_component, 0.01)

    nonlinear_score = (
        (rating_component ** weights["rating"]) *
        (price_component ** weights["price"]) *
        (lead_component ** weights["lead_time"]) *
        (reliability_component ** weights["reliability"]) *
        (risk_component ** weights["risk"])
    )

    return round(nonlinear_score * 100, 2)

def calculate_topsis_scores(raw_candidates, weights):
    """
    TOPSIS baseline.
    Все критерии уже приведены к виду: больше = лучше.
    """

    if not raw_candidates:
        return {}

    criteria = [
        "rating_score",
        "price_score",
        "lead_time_score",
        "reliability_score",
        "risk_component"
    ]

    criteria_weights = {
        "rating_score": weights["rating"],
        "price_score": weights["price"],
        "lead_time_score": weights["lead_time"],
        "reliability_score": weights["reliability"],
        "risk_component": weights["risk"],
    }

    # 1. Нормализация по векторной норме
    denominators = {}

    for c in criteria:
        denominators[c] = sum((item[c] ** 2 for item in raw_candidates)) ** 0.5
        if denominators[c] == 0:
            denominators[c] = 1

    normalized = []

    for item in raw_candidates:
        row = {
            "supplier_id": item["supplier_id"]
        }

        for c in criteria:
            row[c] = (item[c] / denominators[c]) * criteria_weights[c]

        normalized.append(row)

    # 2. Идеальное и анти-идеальное решение
    ideal = {}
    anti_ideal = {}

    for c in criteria:
        values = [row[c] for row in normalized]
        ideal[c] = max(values)
        anti_ideal[c] = min(values)

    # 3. Расстояния и коэффициент близости
    result = {}

    for row in normalized:
        d_plus = sum((row[c] - ideal[c]) ** 2 for c in criteria) ** 0.5
        d_minus = sum((row[c] - anti_ideal[c]) ** 2 for c in criteria) ** 0.5

        if d_plus + d_minus == 0:
            closeness = 0
        else:
            closeness = d_minus / (d_plus + d_minus)

        result[row["supplier_id"]] = round(closeness * 100, 2)

    return result

def score_suppliers_for_material(material_id, scenario="balanced"):
    """
    Главная функция скоринга.
    Её вызывает API логиста.
    """

    rows = SupplierMaterial.query.filter_by(
        material_id=material_id,
        is_active=True
    ).all()

    prices = [float(r.price) for r in rows if r.price is not None]
    lead_times = [int(r.lead_time_days) for r in rows if r.lead_time_days is not None]

    min_price = min(prices) if prices else None
    max_price = max(prices) if prices else None

    min_lead = min(lead_times) if lead_times else None
    max_lead = max(lead_times) if lead_times else None

    ahp_matrix = get_ahp_matrix_by_scenario(scenario)
    ahp_weights = calculate_ahp_weights(ahp_matrix)

    weights = {
        "rating": ahp_weights[0],
        "price": ahp_weights[1],
        "lead_time": ahp_weights[2],
        "reliability": ahp_weights[3],
        "risk": ahp_weights[4],
    }

    candidates = []
    raw_candidates_for_topsis = []

    for relation in rows:
        supplier = relation.supplier

        if not supplier or not supplier.is_active:
            continue

        rating = float(supplier.rating or 0)
        price = float(relation.price) if relation.price is not None else None
        lead_time = int(relation.lead_time_days) if relation.lead_time_days is not None else None

        rating_score = max(0, min(1, rating / 5))
        price_score = normalize_cost(price, min_price, max_price)
        lead_time_score = normalize_cost(lead_time, min_lead, max_lead)

        reliability_data = calculate_supplier_reliability(supplier.id)
        total_deliveries = reliability_data["total_deliveries"]
        completed_deliveries = reliability_data["completed_deliveries"]
        reliability_score = reliability_data["reliability_score"]

        risk_data = calculate_supplier_risk(supplier.id, total_deliveries)
        risk_score = risk_data["risk_score"]
        avg_delay = risk_data["avg_delay"]
        bad_quality_count = risk_data["bad_quality_count"]



        ml_risk_probability = predict_supplier_risk({
            "price": price or 0,
            "lead_time_days": lead_time or 0,
            "supplier_rating": rating or 0,
            "quantity": 0,
            "duration_min": 0,
            "delay_minutes": avg_delay or 0,
            "quality_score": 0
        })

        if ml_risk_probability is not None:
            combined_risk_score = round((0.6 * risk_score) + (0.4 * ml_risk_probability), 3)
        else:
            combined_risk_score = risk_score

        if ml_risk_probability is not None:
            ml_risk_percent = round(100 * ml_risk_probability, 1)
        else:
            ml_risk_percent = None

        final_score = calculate_nonlinear_score(
            rating_score=rating_score,
            price_score=price_score,
            lead_time_score=lead_time_score,
            reliability_score=reliability_score,
            risk_score=combined_risk_score,
            weights=weights
        )

        reasons = build_reasons(
            price_score=price_score,
            rating_score=rating_score,
            lead_time_score=lead_time_score,
            reliability_score=reliability_score,
            risk_score=combined_risk_score
        )
        risk_component = max(1 - combined_risk_score, 0.01)
        raw_candidates_for_topsis.append({
            "supplier_id": supplier.id,
            "rating_score": rating_score,
            "price_score": price_score,
            "lead_time_score": lead_time_score,
            "reliability_score": reliability_score,
            "risk_component": risk_component
        })

        candidates.append({
            'supplier_id': supplier.id,
            'supplier': supplier.company_name,

            'rating': rating,
            'price': price,
            'lead_time_days': lead_time,

            'score': final_score,

            'rating_score': round(rating_score, 3),
            'price_score': round(price_score, 3),
            'lead_time_score': round(lead_time_score, 3),
            'reliability_score': round(reliability_score, 3),
            'risk_score': round(combined_risk_score, 3),
            'rule_risk_score': round(risk_score, 3),
            'ml_risk_probability': ml_risk_probability,
            'ml_risk_percent': round((ml_risk_probability or 0) * 100, 1),

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
            "reliability": round(weights["reliability"], 3),
            "risk": round(weights["risk"], 3),
        },
        "items": candidates
    }