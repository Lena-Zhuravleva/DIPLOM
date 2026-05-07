import datetime
from flask import Blueprint, jsonify, request, session
from decorators import role_required
from extensions import db
from models import Request, Material, Delivery, Supplier, SupplierMaterial, UnloadingFact, ProcurementPlan, SupplierRatingHistory, SupplierEvent
from helpers.scheduler import (
    UNLOAD_PLACES,
    generate_slots,
    time_to_minutes,
    overlaps,
    supplier_candidates,
    slot_busy,
)

api_logistician_bp = Blueprint('api_logistician', __name__)


@api_logistician_bp.route('/api/logistician/requests')
@role_required('logistician')
def logistician_requests():
    reqs = Request.query.order_by(Request.created_at.desc()).all()
    return jsonify([{
        'id': r.id,
        'type': r.type,
        'material_id': r.material_id,
        'material': r.material.name if r.material else None,
        'material_status': r.material.status if r.material else None,
        'quantity': r.quantity,
        'requested_date': r.requested_date.isoformat() if r.requested_date else None,
        'requested_time_slot': r.requested_time_slot.strftime('%H:%M') if r.requested_time_slot else None,
        'supplier_id': r.supplier_id,
        'supplier': r.supplier.company_name if r.supplier else None,
        'status': r.status,
        'notes': r.notes,
        'created_at': r.created_at.isoformat() if r.created_at else None
    } for r in reqs])


@api_logistician_bp.route('/api/logistician/suppliers')
@role_required('logistician')
def logistician_suppliers():
    material_id = request.args.get('material_id', type=int)
    if not material_id:
        return jsonify([])

    rows = SupplierMaterial.query.filter_by(material_id=material_id).all()
    suppliers = [row.supplier for row in rows if row.supplier and row.supplier.is_active]

    return jsonify([{
        'id': s.id,
        'company_name': s.company_name,
        'rating': float(s.rating or 0),
        'delivery_zone': s.delivery_zone
    } for s in suppliers])


@api_logistician_bp.route('/api/logistician/requests/<int:req_id>/approve', methods=['POST'])
@role_required('logistician')
def approve_request(req_id):
    r = Request.query.get_or_404(req_id)
    data = request.json or {}

    delivery_date = datetime.date.fromisoformat(data['delivery_date'])
    delivery_time = datetime.time.fromisoformat(data['delivery_time'])
    supplier_id = int(data['supplier_id'])
    duration_min = int(data.get('duration_min') or 60)

    unload_place = data.get('unload_place') or r.unload_place
    if not unload_place:
        return jsonify({'success': False, 'error': 'Не выбрано место разгрузки'}), 400

    if slot_busy(delivery_date, delivery_time, unload_place):
        return jsonify({'success': False, 'error': 'Слот уже занят'}), 409

    r.status = 'approved'
    r.supplier_id = supplier_id
    r.requested_date = delivery_date
    r.requested_time_slot = delivery_time
    r.duration_min = duration_min
    r.unload_place = unload_place

    delivery = Delivery(
        date=delivery_date,
        time_slot=delivery_time,
        supplier_id=supplier_id,
        material_id=r.material_id,
        quantity=r.quantity or 0,
        status='planned',
        created_by=session['user_id'],
        unload_place=unload_place,
        duration_min=duration_min
    )

    db.session.add(delivery)
    db.session.commit()

    return jsonify({'success': True, 'delivery_id': delivery.id})

@api_logistician_bp.route('/api/logistician/requests/<int:req_id>/reject', methods=['POST'])
@role_required('logistician')
def reject_request(req_id):
    r = Request.query.get_or_404(req_id)
    r.status = 'rejected'
    db.session.commit()
    return jsonify({'success': True})


@api_logistician_bp.route('/api/logistician/calendar')
@role_required('logistician')
def logistician_calendar():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'success': False, 'error': 'date is required'}), 400

    day = datetime.date.fromisoformat(date_str)
    slots = generate_slots(start_hour=8, end_hour=18, step_minutes=15)

    deliveries = Delivery.query.filter_by(date=day).all()
    pending = Request.query.filter(
        Request.requested_date == day,
        Request.status.in_(['pending_logistician', 'pending_supplier', 'reschedule_requested'])
    ).all()
    facts = UnloadingFact.query.filter_by(date=day).all()

    deliveries_by_place = {}
    for d in deliveries:
        if d.time_slot and d.unload_place:
            deliveries_by_place.setdefault(d.unload_place, []).append(d)

    pending_by_place = {}
    for r in pending:
        if r.requested_time_slot and r.unload_place:
            pending_by_place.setdefault(r.unload_place, []).append(r)

    facts_by_place = {}
    for f in facts:
        if f.start_time and f.unload_place:
            facts_by_place.setdefault(f.unload_place, []).append(f)

    rows = []
    for t in slots:
        time_str = f"{t.hour:02d}:{t.minute:02d}"
        slot_min = time_to_minutes(t)
        cells = {}

        for p in UNLOAD_PLACES:
            pid = p["id"]
            plan = None

            for d in deliveries_by_place.get(pid, []):
                d_start = time_to_minutes(d.time_slot)
                d_dur = int(getattr(d, "duration_min", 15) or 15)
                if overlaps(d_start, d_dur, slot_min):
                    plan = {
                        "kind": "delivery",
                        "id": d.id,
                        "supplier_id": d.supplier_id,
                        "supplier": d.supplier.company_name if d.supplier else None,
                        "material": d.material.name if d.material else None,
                        "quantity": d.quantity,
                        "status": d.status,
                        "unload_place": d.unload_place,
                        "duration_min": d_dur
                    }
                    break

            if plan is None:
                for r in pending_by_place.get(pid, []):
                    r_start = time_to_minutes(r.requested_time_slot)
                    r_dur = int(getattr(r, "duration_min", 15) or 15)
                    if overlaps(r_start, r_dur, slot_min):
                        plan = {
                            "kind": "request",
                            "id": r.id,
                            "type": r.type,
                            "status": r.status,
                            "material_id": r.material_id,
                            "material": r.material.name if r.material else None,
                            "quantity": r.quantity,
                            "supplier_id": r.supplier_id,
                            "supplier": r.supplier.company_name if r.supplier else None,
                            "notes": r.notes,
                            "unload_place": r.unload_place,
                            "duration_min": r_dur
                        }
                        break

            fact = None
            for f in facts_by_place.get(pid, []):
                f_start = time_to_minutes(f.start_time)
                f_dur = int(f.duration_min or 15)
                if overlaps(f_start, f_dur, slot_min):
                    fact = {
                        "id": f.id,
                        "status": f.status,
                        "delivery_id": f.delivery_id,
                        "notes": f.notes,
                        "unload_place": f.unload_place,
                        "duration_min": f_dur
                    }
                    break

            cells[pid] = {"plan": plan, "fact": fact}

        rows.append({"time": time_str, "cells": cells})

    return jsonify({
        "success": True,
        "date": day.isoformat(),
        "places": UNLOAD_PLACES,
        "rows": rows
    })


@api_logistician_bp.route('/api/logistician/create_request', methods=['POST'])
@role_required('logistician')
def logistician_create_request():
    data = request.json or {}

    try:
        material_id = int(data.get('material_id'))
        supplier_id = int(data.get('supplier_id'))
        quantity = int(data.get('quantity'))
        requested_date = datetime.date.fromisoformat(data.get('requested_date'))
        requested_time_slot = datetime.time.fromisoformat(data.get('requested_time_slot'))

        duration_min = int(data.get('duration_min') or 15)
        unload_place = data.get('unload_place')

        if not unload_place:
            return jsonify({'success': False, 'error': 'unload_place is required'}), 400

    except Exception:
        return jsonify({'success': False, 'error': 'Некорректные данные формы'}), 400

    r = Request(
        type='logistic_order',
        material_id=material_id,
        supplier_id=supplier_id,
        quantity=quantity,
        requested_date=requested_date,
        requested_time_slot=requested_time_slot,
        duration_min=duration_min,
        unload_place=unload_place,
        created_by=session['user_id'],
        status='pending_supplier',
        notes=data.get('notes')
    )
    db.session.add(r)
    db.session.flush()

    event = SupplierEvent(
        supplier_id=supplier_id,
        material_id=material_id,
        request_id=r.id,
        event_type='request_created',
        description='Логист создал заявку поставщику'
    )

    db.session.add(event)
    db.session.commit()
    return jsonify({'success': True, 'request_id': r.id})

# все поставщики
@api_logistician_bp.route('/api/logistician/all_suppliers')
@role_required('logistician')
def logistician_all_suppliers():
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.company_name.asc()).all()
    return jsonify([{'id': s.id, 'company_name': s.company_name} for s in suppliers])
# все материалы
@api_logistician_bp.route('/api/logistician/all_materials')
@role_required('logistician')
def logistician_all_materials():
    materials = Material.query.order_by(Material.name.asc()).all()
    return jsonify([
        {
            'id': m.id,
            'name': m.name,
            'unit': m.unit
        }
        for m in materials
    ])

@api_logistician_bp.route('/api/logistician/supplier_materials')
@role_required('logistician')
def logistician_supplier_materials():
    supplier_id = request.args.get('supplier_id', type=int)
    if not supplier_id:
        return jsonify([])

    rows = SupplierMaterial.query.filter_by(supplier_id=supplier_id).all()
    mats = [r.material for r in rows if r.material]

    return jsonify([{'id': m.id, 'name': m.name, 'unit': m.unit} for m in mats])

# план в модалке
@api_logistician_bp.route('/api/logistician/procurement-plan')
@role_required('logistician')
def logistician_procurement_plan_api():
    items = ProcurementPlan.query.order_by(ProcurementPlan.planned_date.asc()).all()

    return jsonify({
        'success': True,
        'items': [{
            'id': item.id,
            'material': item.material.name if item.material else None,
            'current_stock': item.material.current_stock if item.material else None,
            'min_stock_level': item.material.min_stock_level if item.material else None,
            'material_status': item.material.status if item.material else None,
            'quantity': item.quantity,
            'planned_date': item.planned_date.isoformat() if item.planned_date else None,
            'status': item.status,
            'notes': item.notes
        } for item in items]
    })

# удаление заявки
@api_logistician_bp.route('/api/logistician/requests/<int:req_id>/delete', methods=['POST'])
@role_required('logistician')
def delete_request(req_id):
    r = Request.query.get_or_404(req_id)

    r.status = 'rejected'
    db.session.commit()

    return jsonify({'success': True})

# удаление поставки
@api_logistician_bp.route('/api/logistician/deliveries/<int:delivery_id>/delete', methods=['POST'])
@role_required('logistician')
def delete_delivery(delivery_id):
    d = Delivery.query.get_or_404(delivery_id)

    d.status = 'cancelled'
    event = SupplierEvent(
        supplier_id=d.supplier_id,
        material_id=d.material_id,
        delivery_id=d.id,
        event_type='delivery_cancelled',
        description='Поставка отменена логистом'
    )

    db.session.add(event)
    db.session.commit()

    return jsonify({'success': True})

# Отметка выполнения заявки
@api_logistician_bp.route('/api/logistician/deliveries/<int:delivery_id>/complete', methods=['POST'])
@role_required('logistician')
def complete_delivery(delivery_id):
    d = Delivery.query.get_or_404(delivery_id)
    data = request.json or {}

    try:
        actual_date = datetime.date.fromisoformat(data.get('actual_date'))
        actual_time = datetime.time.fromisoformat(data.get('actual_time'))
        quality_score = int(data.get('quality_score') or 5)
        result_notes = data.get('result_notes')
    except Exception:
        return jsonify({'success': False, 'error': 'Некорректные данные факта'}), 400

    planned_dt = datetime.datetime.combine(d.date, d.time_slot)
    actual_dt = datetime.datetime.combine(actual_date, actual_time)

    delay_minutes = int((actual_dt - planned_dt).total_seconds() // 60)
    delay_minutes = max(0, delay_minutes)

    supplier = d.supplier
    if not supplier:
        return jsonify({'success': False, 'error': 'У поставки не указан поставщик'}), 400

    old_rating = float(supplier.rating or 5)

    delivery_score = float(quality_score)

    # штраф за задержку
    if delay_minutes > 120:
        delivery_score -= 1.0
    elif delay_minutes > 60:
        delivery_score -= 0.7
    elif delay_minutes > 30:
        delivery_score -= 0.3

    # ограничение
    delivery_score = max(1, min(5, delivery_score))

    # новая оценка (сглаживание)
    new_rating = old_rating * 0.8 + delivery_score * 0.2

    # округление
    new_rating = round(new_rating, 2)

    supplier.rating = new_rating

    d.actual_date = actual_date
    d.actual_time = actual_time
    d.delay_minutes = delay_minutes
    d.quality_score = quality_score
    d.result_notes = result_notes
    d.status = 'delivered'

    history = SupplierRatingHistory(
        supplier_id=supplier.id,
        delivery_id=d.id,
        old_rating=old_rating,
        new_rating=new_rating,
        quality_score=quality_score,
        delay_minutes=delay_minutes,
        reason='completion_update'
    )

    db.session.add(history)
    event = SupplierEvent(
        supplier_id=supplier.id,
        material_id=d.material_id,
        delivery_id=d.id,
        event_type='delivery_completed',
        event_value=quality_score,
        description=f'Поставка выполнена. Задержка: {delay_minutes} мин, оценка качества: {quality_score}'
    )

    db.session.add(event)

    db.session.commit()

    return jsonify({'success': True})


# Для отображения поставок всех
@api_logistician_bp.route('/api/logistician/deliveries')
@role_required('logistician')
def logistician_deliveries():
    deliveries = Delivery.query.order_by(Delivery.date.desc(), Delivery.time_slot.desc()).all()

    return jsonify([{
        'id': d.id,
        'date': d.date.isoformat() if d.date else None,
        'time_slot': d.time_slot.strftime('%H:%M') if d.time_slot else None,
        'supplier': d.supplier.company_name if d.supplier else None,
        'material': d.material.name if d.material else None,
        'quantity': d.quantity,
        'unload_place': d.unload_place,
        'duration_min': d.duration_min,
        'status': d.status,
        'notes': d.notes
    } for d in deliveries])


# рекомендация по выбору поставщика
@api_logistician_bp.route('/api/logistician/recommend-suppliers')
@role_required('logistician')
def recommend_suppliers():
    material_id = request.args.get('material_id', type=int)

    if not material_id:
        return jsonify({'success': False, 'error': 'material_id is required'}), 400

    rows = SupplierMaterial.query.filter_by(
        material_id=material_id,
        is_active=True
    ).all()

    candidates = []

    prices = [float(r.price) for r in rows if r.price]
    lead_times = [int(r.lead_time_days) for r in rows if r.lead_time_days]

    min_price = min(prices) if prices else None
    max_price = max(prices) if prices else None
    min_lead = min(lead_times) if lead_times else None
    max_lead = max(lead_times) if lead_times else None

    for r in rows:
        s = r.supplier
        if not s or not s.is_active:
            continue

        rating = float(s.rating or 0)
        price = float(r.price) if r.price else None
        lead_time = int(r.lead_time_days) if r.lead_time_days else None

        rating_score = rating / 5

        total_deliveries = Delivery.query.filter_by(supplier_id=s.id).count()
        completed_deliveries = Delivery.query.filter_by(
            supplier_id=s.id,
            status='delivered'
        ).count()

        reliability_score = completed_deliveries / total_deliveries if total_deliveries > 0 else 0.5

        delivered_rows = Delivery.query.filter(
            Delivery.supplier_id == s.id,
            Delivery.status == 'delivered',
            Delivery.delay_minutes.isnot(None)
        ).all()

        avg_delay = (
            sum(d.delay_minutes for d in delivered_rows) / len(delivered_rows)
            if delivered_rows else 0
        )

        bad_quality_count = Delivery.query.filter(
            Delivery.supplier_id == s.id,
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

        if price and min_price is not None and max_price is not None and max_price != min_price:
            price_score = 1 - ((price - min_price) / (max_price - min_price))
        else:
            price_score = 0.5

        if lead_time and min_lead is not None and max_lead is not None and max_lead != min_lead:
            lead_time_score = 1 - ((lead_time - min_lead) / (max_lead - min_lead))
        else:
            lead_time_score = 0.5

        reasons = []

        if price_score > 0.8:
            reasons.append('выгодная цена')

        if rating_score > 0.8:
            reasons.append('высокий рейтинг')

        if reliability_score > 0.7:
            reasons.append('надежный поставщик')

        if risk_score > 0.5:
            reasons.append('есть риск задержек')

        if not reasons:
            reasons.append('сбалансированные показатели')

        score = (
            0.30 * rating_score +
            0.25 * price_score +
            0.20 * lead_time_score +
            0.15 * reliability_score -
            0.10 * risk_score
        )

        candidates.append({
            'supplier_id': s.id,
            'supplier': s.company_name,
            'rating': rating,
            'price': price,
            'lead_time_days': lead_time,
            'score': round(score, 3),
            'reliability_score': round(reliability_score, 3),
            'risk_score': round(risk_score, 3),
            'avg_delay': round(avg_delay, 1),
            'bad_quality_count': bad_quality_count,
            'total_deliveries': total_deliveries,
            'completed_deliveries': completed_deliveries,
            'reasons': reasons,
        })

    candidates.sort(key=lambda x: x['score'], reverse=True)

    return jsonify({'success': True, 'items': candidates})

# отображение рейтинга поставщика у логиста
@api_logistician_bp.route('/api/logistician/supplier-summary/<int:supplier_id>')
@role_required('logistician')
def supplier_summary(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)

    deliveries = Delivery.query.filter_by(supplier_id=supplier.id).all()

    total = len(deliveries)
    delivered = len([d for d in deliveries if d.status == 'delivered'])
    cancelled = len([d for d in deliveries if d.status == 'cancelled'])
    planned = len([d for d in deliveries if d.status == 'planned'])

    reliability = delivered / total if total > 0 else 0

    delays = [
        d.delay_minutes for d in deliveries
        if d.delay_minutes is not None and d.status == 'delivered'
    ]

    avg_delay = round(sum(delays) / len(delays), 1) if delays else 0

    qualities = [
        d.quality_score for d in deliveries
        if d.quality_score is not None and d.status == 'delivered'
    ]

    avg_quality = round(sum(qualities) / len(qualities), 2) if qualities else 0

    recent_events = (SupplierEvent.query
        .filter_by(supplier_id=supplier.id)
        .order_by(SupplierEvent.created_at.desc())
        .limit(5)
        .all())

    return jsonify({
        'success': True,
        'supplier': {
            'id': supplier.id,
            'company_name': supplier.company_name,
            'rating': float(supplier.rating or 0),
            'delivery_zone': supplier.delivery_zone,
            'is_active': supplier.is_active
        },
        'stats': {
            'total': total,
            'delivered': delivered,
            'cancelled': cancelled,
            'planned': planned,
            'reliability': round(reliability, 2),
            'avg_delay': avg_delay,
            'avg_quality': avg_quality
        },
        'events': [{
            'event_type': e.event_type,
            'description': e.description,
            'created_at': e.created_at.strftime('%d.%m.%Y %H:%M') if e.created_at else None
        } for e in recent_events]
    })