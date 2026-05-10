from models import Delivery, SupplierMaterial


def delivery_target_is_problem(delivery):
    """
    Целевая переменная для ML.
    1 = проблемная поставка
    0 = нормальная поставка
    """

    if delivery.status == 'cancelled':
        return 1

    if delivery.delay_minutes is not None and delivery.delay_minutes > 30:
        return 1

    if delivery.quality_score is not None and delivery.quality_score <= 2:
        return 1

    return 0


def build_supplier_ml_dataset():
    """
    Собирает dataset для обучения модели риска поставщика.
    Пока возвращает список словарей.
    Потом этот список можно будет передать в pandas/sklearn.
    """

    deliveries = Delivery.query.filter(
        Delivery.supplier_id.isnot(None),
        Delivery.material_id.isnot(None),
        Delivery.status.in_(['delivered', 'cancelled'])
    ).all()

    rows = []

    for d in deliveries:
        supplier = d.supplier
        material = d.material

        if not supplier or not material:
            continue

        relation = SupplierMaterial.query.filter_by(
            supplier_id=supplier.id,
            material_id=material.id
        ).first()

        price = float(relation.price) if relation and relation.price is not None else None
        lead_time_days = relation.lead_time_days if relation else None

        row = {
            "delivery_id": d.id,
            "supplier_id": supplier.id,
            "material_id": material.id,

            "price": price,
            "lead_time_days": lead_time_days,
            "supplier_rating": float(supplier.rating or 0),

            "quantity": float(d.quantity or 0),
            "duration_min": int(d.duration_min or 0),

            "delay_minutes": int(d.delay_minutes or 0),
            "quality_score": int(d.quality_score or 0),

            "status": d.status,
            "target_problem": delivery_target_is_problem(d)
        }

        rows.append(row)

    return rows