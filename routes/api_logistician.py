import datetime
from flask import Blueprint, jsonify, request, session
from decorators import role_required
from extensions import db
from models import Request, Material, Delivery, Supplier, SupplierMaterial, UnloadingFact, ProcurementPlan
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
    reqs = Request.query.filter_by(status='pending_logistician').order_by(Request.created_at.desc()).all()
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
    suppliers = [row.supplier for row in rows if row.supplier]

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
    db.session.commit()
    return jsonify({'success': True, 'request_id': r.id})

# все поставщики
@api_logistician_bp.route('/api/logistician/all_suppliers')
@role_required('logistician')
def logistician_all_suppliers():
    suppliers = Supplier.query.order_by(Supplier.company_name.asc()).all()
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

    db.session.delete(r)
    db.session.commit()

    return jsonify({'success': True})

# удаление поставки
@api_logistician_bp.route('/api/logistician/deliveries/<int:delivery_id>/delete', methods=['POST'])
@role_required('logistician')
def delete_delivery(delivery_id):
    d = Delivery.query.get_or_404(delivery_id)

    db.session.delete(d)
    db.session.commit()

    return jsonify({'success': True})