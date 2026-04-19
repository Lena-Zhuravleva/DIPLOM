import datetime
from flask import Blueprint, request, jsonify, session
from decorators import role_required
from models import Delivery, Request, Supplier, SupplierMaterial
from extensions import db
from helpers.scheduler import generate_slots, time_to_minutes, overlaps, UNLOAD_PLACES, slot_busy

api_supplier_bp = Blueprint('api_supplier', __name__, url_prefix='/api/supplier')


@api_supplier_bp.get('/calendar')
@role_required('supplier')
def supplier_calendar():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'success': False, 'error': 'date is required'}), 400

    day = datetime.date.fromisoformat(date_str)
    slots = generate_slots(start_hour=8, end_hour=18, step_minutes=15)

    deliveries = Delivery.query.filter_by(date=day).all()
    pending = Request.query.filter(
        Request.requested_date == day,
        Request.status.in_(['pending_supplier', 'reschedule_requested'])
    ).all()

    deliveries_by_place = {}
    for d in deliveries:
        if d.time_slot and d.unload_place:
            deliveries_by_place.setdefault(d.unload_place, []).append(d)

    pending_by_place = {}
    for r in pending:
        if r.requested_time_slot and r.unload_place:
            pending_by_place.setdefault(r.unload_place, []).append(r)

    rows = []
    for t in slots:
        time_str = f"{t.hour:02d}:{t.minute:02d}"
        slot_min = time_to_minutes(t)
        cells = {}

        for p in UNLOAD_PLACES:
            pid = p["id"]
            state = {"status": "free", "label": None}  # free | busy | pending

            for d in deliveries_by_place.get(pid, []):
                d_start = time_to_minutes(d.time_slot)
                d_dur = int(getattr(d, "duration_min", 15) or 15)
                if overlaps(d_start, d_dur, slot_min):
                    state = {"status": "busy", "label": "Занято"}
                    break

            if state["status"] == "free":
                for r in pending_by_place.get(pid, []):
                    r_start = time_to_minutes(r.requested_time_slot)
                    r_dur = int(getattr(r, "duration_min", 15) or 15)
                    if overlaps(r_start, r_dur, slot_min):
                        state = {"status": "pending", "label": "Ожидает"}
                        break

            cells[pid] = state

        rows.append({"time": time_str, "cells": cells})

    return jsonify({"success": True, "date": day.isoformat(), "places": UNLOAD_PLACES, "rows": rows})


@api_supplier_bp.get('/materials')
@role_required('supplier')
def supplier_materials():
    supplier = Supplier.query.filter_by(user_id=session['user_id']).first()
    if not supplier:
        return jsonify({'success': False, 'error': 'Supplier not found'}), 404

    rows = SupplierMaterial.query.filter_by(supplier_id=supplier.id).all()
    mats = [r.material for r in rows if r.material]

    return jsonify({
        'success': True,
        'items': [{
            'id': m.id,
            'name': m.name,
            'category': m.category,
            'unit': m.unit
        } for m in mats]
    })


@api_supplier_bp.post('/book')
@role_required('supplier')
def supplier_book():
    supplier = Supplier.query.filter_by(user_id=session['user_id']).first()
    if not supplier:
        return jsonify({'success': False, 'error': 'Supplier not found'}), 404

    data = request.json or {}

    try:
        material_id = int(data.get('material_id'))
        quantity = int(data.get('quantity') or 0)
        requested_date = datetime.date.fromisoformat(data.get('requested_date'))
        requested_time_slot = datetime.time.fromisoformat(data.get('requested_time_slot'))
        unload_place = data.get('unload_place')
        duration_min = int(data.get('duration_min') or 15)
        notes = data.get('notes')

        if quantity <= 0:
            return jsonify({'success': False, 'error': 'quantity must be > 0'}), 400
        if not unload_place:
            return jsonify({'success': False, 'error': 'unload_place is required'}), 400

    except Exception:
        return jsonify({'success': False, 'error': 'Некорректные данные'}), 400

    req = Request(
        type='supplier_booking',
        material_id=material_id,
        quantity=quantity,
        supplier_id=supplier.id,
        requested_date=requested_date,
        requested_time_slot=requested_time_slot,
        unload_place=unload_place,
        duration_min=duration_min,
        created_by=session['user_id'],
        status='pending_logistician',
        notes=notes
    )

    db.session.add(req)
    db.session.commit()

    return jsonify({'success': True, 'request_id': req.id})

@api_supplier_bp.get('/requests')
@role_required('supplier')
def supplier_requests():
    supplier = Supplier.query.filter_by(user_id=session['user_id']).first()
    if not supplier:
        return jsonify({'success': False, 'error': 'Supplier not found'}), 404

    reqs = (Request.query
            .filter_by(supplier_id=supplier.id)
            .order_by(Request.created_at.desc())
            .all())

    return jsonify({
        'success': True,
        'items': [{
            'id': r.id,
            'material': r.material.name if r.material else None,
            'quantity': r.quantity,
            'requested_date': r.requested_date.isoformat() if r.requested_date else None,
            'requested_time_slot': r.requested_time_slot.strftime('%H:%M') if r.requested_time_slot else None,
            'unload_place': r.unload_place,
            'status': r.status,
            'created_at': r.created_at.isoformat() if r.created_at else None
        } for r in reqs]
    })
# Подтвердить слот
@api_supplier_bp.post('/requests/<int:req_id>/confirm')
@role_required('supplier')
def supplier_confirm_request(req_id):
    supplier = Supplier.query.filter_by(user_id=session['user_id']).first()
    if not supplier:
        return jsonify({'success': False, 'error': 'Supplier not found'}), 404

    r = Request.query.get_or_404(req_id)

    if r.supplier_id != supplier.id:
        return jsonify({'success': False, 'error': 'Нет доступа к заявке'}), 403

    if r.status != 'pending_supplier':
        return jsonify({'success': False, 'error': 'Заявка уже обработана'}), 400

    data = request.json or {}

    try:
        delivery_date = datetime.date.fromisoformat(data.get('delivery_date'))
        delivery_time = datetime.time.fromisoformat(data.get('delivery_time'))
    except Exception:
        return jsonify({'success': False, 'error': 'Некорректные дата или время'}), 400

    unload_place = r.unload_place
    duration_min = int(r.duration_min or 15)

    deliveries = Delivery.query.filter_by(date=delivery_date, unload_place=unload_place).all()
    slot_min = time_to_minutes(delivery_time)

    for d in deliveries:
        d_start = time_to_minutes(d.time_slot)
        d_dur = int(d.duration_min or 15)
        if overlaps(d_start, d_dur, slot_min):
            return jsonify({'success': False, 'error': 'Слот уже занят'}), 409

    delivery = Delivery(
        date=delivery_date,
        time_slot=delivery_time,
        supplier_id=r.supplier_id,
        material_id=r.material_id,
        quantity=r.quantity or 0,
        status='planned',
        created_by=session['user_id'],
        unload_place=unload_place,
        duration_min=duration_min,
        notes=r.notes
    )

    r.requested_date = delivery_date
    r.requested_time_slot = delivery_time
    r.status = 'confirmed_supplier'

    db.session.add(delivery)
    db.session.commit()

    return jsonify({'success': True, 'delivery_id': delivery.id})
# Запросить перенос
@api_supplier_bp.post('/requests/<int:req_id>/reschedule')
@role_required('supplier')
def supplier_reschedule_request(req_id):
    supplier = Supplier.query.filter_by(user_id=session['user_id']).first()
    if not supplier:
        return jsonify({'success': False, 'error': 'Supplier not found'}), 404

    r = Request.query.get_or_404(req_id)

    if r.supplier_id != supplier.id:
        return jsonify({'success': False, 'error': 'Нет доступа к заявке'}), 403

    if r.status != 'pending_supplier':
        return jsonify({'success': False, 'error': 'Заявка уже обработана'}), 400

    r.status = 'reschedule_requested'
    db.session.commit()

    return jsonify({'success': True})

# Отказаться
@api_supplier_bp.post('/requests/<int:req_id>/reject')
@role_required('supplier')
def supplier_reject_request(req_id):
    supplier = Supplier.query.filter_by(user_id=session['user_id']).first()
    if not supplier:
        return jsonify({'success': False, 'error': 'Supplier not found'}), 404

    r = Request.query.get_or_404(req_id)

    if r.supplier_id != supplier.id:
        return jsonify({'success': False, 'error': 'Нет доступа к заявке'}), 403

    if r.status != 'pending_supplier':
        return jsonify({'success': False, 'error': 'Заявка уже обработана'}), 400

    r.status = 'rejected_supplier'
    db.session.commit()

    return jsonify({'success': True})
