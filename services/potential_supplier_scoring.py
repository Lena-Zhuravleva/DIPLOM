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

    min_price = min(prices) if prices else price
    max_price = max(prices) if prices else price

    min_lead = min(lead_times) if lead_times else lead_time_days
    max_lead = max(lead_times) if lead_times else lead_time_days

    ahp_matrix = get_ahp_matrix_by_scenario(scenario)
    ahp_weights = calculate_ahp_weights(ahp_matrix)

    weights = {
        "rating": ahp_weights[0],
        "price": ahp_weights[1],
        "lead_time": ahp_weights[2],
        "reliability": ahp_weights[3],
        "risk": ahp_weights[4],
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

    return {
        "rating_score": round(rating_score, 3),
        "price_score": round(price_score, 3),
        "lead_time_score": round(lead_time_score, 3),
        "reliability_score": round(reliability_score, 3),
        "risk_score": round(risk_score, 3),
        "hybrid_score": hybrid_score,
        "weights": weights
    }