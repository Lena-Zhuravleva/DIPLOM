from flask import Blueprint, request, redirect, url_for, flash, render_template, session
from decorators import role_required
import datetime
from extensions import db
from models import User, Supplier, Material, Request, ProcurementPlan, SupplierMaterial, Delivery, SupplierRatingHistory, SupplierEvent, PotentialSupplier
from services.ml_dataset import build_supplier_ml_dataset
from services.ml_training import predict_supplier_risk, train_supplier_risk_model, load_supplier_risk_model, MODEL_PATH
from services.potential_supplier_scoring import score_potential_supplier
from services.review_sentiment import analyze_reviews_text
from services.review_parser import parse_reviews_from_company_name

import os

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/admin/suppliers/create', methods=['POST'])
@role_required('admin')
def admin_create_supplier():
    company_name = request.form.get('company_name', '').strip()
    address = request.form.get('address', '').strip()
    delivery_zone = request.form.get('delivery_zone', 'local')
    specialization = request.form.get('specialization', '').strip()
    contact_person = request.form.get('contact_person', '').strip()
    delivery_time_days = request.form.get('delivery_time_days', '1').strip()

    if not company_name:
        flash('Название компании обязательно', 'error')
        return redirect(url_for('suppliers.suppliers_page'))  # лучше на страницу поставщиков

    try:
        if Supplier.query.filter_by(company_name=company_name).first():
            flash('Поставщик с таким названием уже существует', 'error')
            return redirect(url_for('suppliers.suppliers_page'))

        s = Supplier(
            company_name=company_name,
            address=address or None,
            delivery_zone=delivery_zone,
            specialization=specialization or None,
            contact_person=contact_person or None,
            delivery_time_days=int(delivery_time_days) if delivery_time_days.isdigit() else 1
        )
        db.session.add(s)
        db.session.commit()
        flash('Поставщик добавлен', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при добавлении поставщика: {str(e)}', 'error')

    return redirect(url_for('suppliers.suppliers_page'))


@admin_bp.route('/admin/suppliers/materials/save', methods=['POST'])
@role_required('admin')
def admin_save_supplier_materials():
    supplier_id = request.form.get('supplier_id')
    material_ids = request.form.getlist('material_ids')

    if not supplier_id or not str(supplier_id).isdigit():
        flash('Выберите поставщика', 'error')
        return redirect(url_for('suppliers.suppliers_page'))

    supplier = Supplier.query.get(int(supplier_id))
    if not supplier:
        flash('Поставщик не найден', 'error')
        return redirect(url_for('suppliers.suppliers_page'))

    try:
        SupplierMaterial.query.filter_by(supplier_id=supplier.id).delete()
        for mid in material_ids:
            if str(mid).isdigit():
                db.session.add(SupplierMaterial(supplier_id=supplier.id, material_id=int(mid)))

        db.session.commit()
        flash('Материалы поставщика обновлены', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при сохранении материалов: {str(e)}', 'error')

    return redirect(url_for('suppliers.suppliers_page'))

# редактирование материалов поставщика
@admin_bp.route('/admin/supplier-materials')
@role_required('admin')
def supplier_materials_page():
    suppliers = Supplier.query.order_by(Supplier.company_name.asc()).all()
    materials = Material.query.order_by(Material.name.asc()).all()

    relations = SupplierMaterial.query.all()

    mapping = {}
    for r in relations:
        mapping[(r.supplier_id, r.material_id)] = r

    return render_template(
        'admin/supplier_materials.html',
        suppliers=suppliers,
        materials=materials,
        mapping=mapping
    )

# сохранение материалов поставщика
@admin_bp.route('/admin/supplier-materials/save', methods=['POST'])
@role_required('admin')
def save_supplier_materials_matrix():
    SupplierMaterial.query.delete()

    for key, value in request.form.items():
        if not key.startswith('rel_'):
            continue

        parts = key.split('_')
        supplier_id = int(parts[1])
        material_id = int(parts[2])

        price_raw = request.form.get(f'price_{supplier_id}_{material_id}')
        lead_raw = request.form.get(f'lead_{supplier_id}_{material_id}')

        price = None
        lead_time_days = None

        if price_raw:
            price = float(price_raw)

        if lead_raw:
            lead_time_days = int(lead_raw)

        row = SupplierMaterial(
            supplier_id=supplier_id,
            material_id=material_id,
            price=price,
            lead_time_days=lead_time_days,
            is_active=True
        )

        db.session.add(row)

    db.session.commit()
    return redirect(url_for('admin.supplier_materials_page'))

# ====== USERS (Admin) ======

@admin_bp.route('/admin/users', methods=['GET'])
@role_required('admin')
def admin_users_page():
    users = User.query.order_by(User.id.asc()).all()
    return render_template('admin/register.html', users=users)


@admin_bp.route('/admin/users/create', methods=['POST'])
@role_required('admin')
def admin_users_create():
    username = (request.form.get('username') or '').strip()
    full_name = (request.form.get('full_name') or '').strip()
    password = (request.form.get('password') or '').strip()
    email = (request.form.get('email') or '').strip()
    role = (request.form.get('role') or '').strip()
    phone = (request.form.get('phone') or '').strip() or None

    if not all([username, full_name, password, email, role]):
        flash('Все обязательные поля должны быть заполнены', 'error')
        return redirect(url_for('admin.admin_users_page'))

    if User.query.filter_by(username=username).first():
        flash('Пользователь с таким логином уже существует', 'error')
        return redirect(url_for('admin.admin_users_page'))

    if User.query.filter_by(email=email).first():
        flash('Пользователь с таким email уже существует', 'error')
        return redirect(url_for('admin.admin_users_page'))

    valid_roles = ['admin', 'logistician', 'warehouse', 'supplier', 'viewer']
    if role not in valid_roles:
        flash('Неверная роль пользователя', 'error')
        return redirect(url_for('admin.admin_users_page'))

    try:
        new_user = User(
            username=username,
            full_name=full_name,
            email=email,
            role=role,
            phone=phone,
            is_active=True
        )
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        # если создаём supplier-пользователя — создаём запись supplier (если нет)
        if role == 'supplier':
            if not Supplier.query.filter_by(user_id=new_user.id).first():
                supplier = Supplier(
                    user_id=new_user.id,
                    company_name=full_name,
                    contact_person=full_name
                )
                db.session.add(supplier)
                db.session.commit()

        flash(f'Пользователь {username} успешно зарегистрирован!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при регистрации пользователя: {str(e)}', 'error')

    return redirect(url_for('admin.admin_users_page'))

# таблица плана закупок
@admin_bp.route('/procurement-plan')
@role_required('admin')
def procurement_plan_page():
    materials = Material.query.order_by(Material.name.asc()).all()
    items = ProcurementPlan.query.order_by(ProcurementPlan.planned_date.asc()).all()

    return render_template(
        'admin/procurement_plan.html',
        materials=materials,
        items=items
    )

# создание позиции плана
@admin_bp.route('/procurement-plan/create', methods=['POST'])
@role_required('admin')
def create_procurement_plan_item():
    material_id = request.form.get('material_id', type=int)
    quantity = request.form.get('quantity', type=int)
    planned_date = request.form.get('planned_date')
    notes = request.form.get('notes', default='')

    if not material_id or not quantity or not planned_date:
        return redirect(url_for('admin.procurement_plan_page'))

    item = ProcurementPlan(
        material_id=material_id,
        quantity=quantity,
        planned_date=datetime.date.fromisoformat(planned_date),
        status='planned',
        notes=notes,
        created_by=session['user_id']
    )

    db.session.add(item)
    db.session.commit()

    return redirect(url_for('admin.procurement_plan_page'))

# деактивация пользователя
@admin_bp.route('/admin/users/<int:user_id>/deactivate', methods=['POST'])
@role_required('admin')
def deactivate_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.role == 'admin':
        flash('Администратора нельзя деактивировать через эту кнопку.', 'error')
        return redirect(url_for('admin.admin_users_page'))

    user.is_active = False

    if user.role == 'supplier' and user.supplier:
        user.supplier.is_active = False

    db.session.commit()
    flash('Пользователь деактивирован.', 'success')
    return redirect(url_for('admin.admin_users_page'))

# восстановление пользователя
@admin_bp.route('/admin/users/<int:user_id>/activate', methods=['POST'])
@role_required('admin')
def activate_user(user_id):
    user = User.query.get_or_404(user_id)

    user.is_active = True

    if user.role == 'supplier' and user.supplier:
        user.supplier.is_active = True

    db.session.commit()
    flash('Пользователь восстановлен.', 'success')
    return redirect(url_for('admin.admin_users_page'))

# деактивация поставщика
@admin_bp.route('/admin/suppliers/<int:supplier_id>/deactivate', methods=['POST'])
@role_required('admin')
def deactivate_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)

    supplier.is_active = False

    if supplier.user:
        supplier.user.is_active = False

    db.session.commit()
    flash('Поставщик деактивирован.', 'success')
    return redirect(url_for('suppliers.suppliers_page'))

# восстановление поставщика
@admin_bp.route('/admin/suppliers/<int:supplier_id>/activate', methods=['POST'])
@role_required('admin')
def activate_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)

    supplier.is_active = True

    if supplier.user:
        supplier.user.is_active = True

    db.session.commit()
    flash('Поставщик восстановлен.', 'success')
    return redirect(url_for('suppliers.suppliers_page'))

#хранение истории о поставщике
@admin_bp.route('/admin/supplier-rating')
@role_required('admin')
def supplier_ratings_page():
    suppliers = Supplier.query.order_by(Supplier.rating.desc()).all()

    history = (SupplierRatingHistory.query
               .order_by(SupplierRatingHistory.created_at.desc())
               .limit(100)
               .all())

    stats = []

    for s in suppliers:
        total_deliveries = Delivery.query.filter_by(supplier_id=s.id).count()

        delivered = Delivery.query.filter_by(
            supplier_id=s.id,
            status='delivered'
        ).count()

        cancelled = Delivery.query.filter_by(
            supplier_id=s.id,
            status='cancelled'
        ).count()

        supplier_rejected = Request.query.filter_by(
            supplier_id=s.id,
            status='rejected_supplier'
        ).count()

        total_interactions = total_deliveries + supplier_rejected

        delivered_rows = Delivery.query.filter(
            Delivery.supplier_id == s.id,
            Delivery.status == 'delivered',
            Delivery.delay_minutes.isnot(None)
        ).all()

        if delivered_rows:
            avg_delay = round(sum(d.delay_minutes for d in delivered_rows) / len(delivered_rows), 1)
        else:
            avg_delay = None

        stats.append({
            'supplier': s,
            'total_deliveries': total_deliveries,
            'total_interactions': total_interactions,
            'delivered': delivered,
            'cancelled': cancelled,
            'supplier_rejected': supplier_rejected,
            'avg_delay': avg_delay
        })

    return render_template(
        'admin/supplier_rating.html',
        stats=stats,
        history=history
    )

# роут для отображения журнала действий в системе
@admin_bp.route('/admin/supplier-events')
@role_required('admin')
def supplier_events_page():
    events = (SupplierEvent.query
              .order_by(SupplierEvent.created_at.desc())
              .limit(200)
              .all())

    return render_template(
        'admin/supplier_events.html',
        events=events
    )

# аналитика поставщика
@admin_bp.route('/admin/supplier-analytics/<int:supplier_id>')
@role_required('admin')
def supplier_analytics_page(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)

    deliveries = Delivery.query.filter_by(supplier_id=supplier.id).all()

    total = len(deliveries)
    delivered = len([d for d in deliveries if d.status == 'delivered'])
    cancelled = len([d for d in deliveries if d.status == 'cancelled'])
    planned = len([d for d in deliveries if d.status == 'planned'])

    delivered_with_delay = [
        d for d in deliveries
        if d.status == 'delivered' and d.delay_minutes is not None
    ]

    avg_delay = None
    if delivered_with_delay:
        avg_delay = round(sum(d.delay_minutes for d in delivered_with_delay) / len(delivered_with_delay), 1)

    quality_rows = [
        d for d in deliveries
        if d.status == 'delivered' and d.quality_score is not None
    ]

    avg_quality = None
    if quality_rows:
        avg_quality = round(sum(d.quality_score for d in quality_rows) / len(quality_rows), 2)

    materials = SupplierMaterial.query.filter_by(supplier_id=supplier.id).all()

    events = (SupplierEvent.query
              .filter_by(supplier_id=supplier.id)
              .order_by(SupplierEvent.created_at.desc())
              .limit(50)
              .all())

    rating_history = (SupplierRatingHistory.query
                      .filter_by(supplier_id=supplier.id)
                      .order_by(SupplierRatingHistory.created_at.desc())
                      .limit(50)
                      .all())

    ml_prediction = None
    ml_risk_level = None
    ml_behavior_text = None

    try:
        ml_prediction = predict_supplier_risk({
            "price": 0,
            "lead_time_days": supplier.delivery_time_days or 0,
            "supplier_rating": supplier.rating or 0,
            "quantity": total,
            "duration_min": avg_delay or 0,
            "delay_minutes": avg_delay or 0,
            "quality_score": avg_quality or 4
        })

        if ml_prediction is not None:
            probability = round(ml_prediction * 100, 1)

            if probability < 30:
                ml_risk_level = "Низкий риск"
                ml_behavior_text = (
                    "Поставщик, вероятно, выполнит поставку "
                    "без критических нарушений."
                )

            elif probability < 60:
                ml_risk_level = "Средний риск"
                ml_behavior_text = (
                    "Возможны задержки или снижение качества поставки."
                )

            else:
                ml_risk_level = "Высокий риск"
                ml_behavior_text = (
                    "Высока вероятность проблемной поставки."
                )

    except Exception:
        pass

    return render_template(
        'admin/supplier_analytics.html',
        supplier=supplier,
        total=total,
        delivered=delivered,
        cancelled=cancelled,
        planned=planned,
        avg_delay=avg_delay,
        avg_quality=avg_quality,
        materials=materials,
        events=events,
        ml_prediction=ml_prediction,
        ml_risk_level=ml_risk_level,
        ml_behavior_text=ml_behavior_text,
        rating_history=rating_history
    )

@admin_bp.route('/admin/ml-model')
@role_required('admin')
def ml_model_page():
    rows = build_supplier_ml_dataset()

    normal_count = len([r for r in rows if r.get("target_problem") == 0])
    problem_count = len([r for r in rows if r.get("target_problem") == 1])

    saved_model = load_supplier_risk_model()
    model_exists = saved_model is not None

    metrics = None
    features = []
    model_path = MODEL_PATH
    feature_importance = []

    if saved_model:
        metrics = saved_model.get('metrics')
        features = saved_model.get('feature_columns', [])
        feature_importance = saved_model.get('feature_importance', [])

    return render_template(
        'admin/ml_model.html',
        rows_count=len(rows),
        model_exists=model_exists,
        metrics=metrics,
        features=features,
        model_path=model_path,
        normal_count=normal_count,
        problem_count=problem_count,
        feature_importance=feature_importance
    )


@admin_bp.route('/admin/ml-model/train', methods=['POST'])
@role_required('admin')
def train_ml_model_admin():
    result = train_supplier_risk_model()

    if result.get('success'):
        flash('ML-модель успешно обучена.', 'success')
    else:
        flash(result.get('error', 'Ошибка обучения ML-модели.'), 'error')

    return redirect(url_for('admin.ml_model_page'))

@admin_bp.route('/admin/potential-suppliers')
@role_required('admin')
def potential_suppliers_page():
    items = PotentialSupplier.query.order_by(PotentialSupplier.id.desc()).all()
    return render_template('admin/potential_suppliers.html', items=items)


@admin_bp.route('/admin/potential-suppliers/evaluate', methods=['POST'])
@role_required('admin')
def evaluate_potential_supplier():
    company_name = request.form.get('company_name', '').strip()
    material_query = request.form.get('material_query', '').strip()
    price = request.form.get('price') or None
    lead_time_days = request.form.get('lead_time_days') or None
    city = request.form.get('city', '').strip()
    category = request.form.get('category', '').strip()
    website = request.form.get('website', '').strip()
    reviews_text = request.form.get('reviews_text', '').strip()
    scenario = request.form.get('scenario', 'balanced')

    if not company_name:
        flash('Введите название поставщика', 'error')
        return redirect(url_for('admin.potential_suppliers_page'))

    if not material_query:
        flash('Введите материал или категорию', 'error')
        return redirect(url_for('admin.potential_suppliers_page'))

    if not price:
        flash('Введите цену', 'error')
        return redirect(url_for('admin.potential_suppliers_page'))

    if not lead_time_days:
        flash('Введите срок поставки', 'error')
        return redirect(url_for('admin.potential_suppliers_page'))

    sentiment = analyze_reviews_text(reviews_text)

    scoring = score_potential_supplier(
        material_query=material_query,
        price=price,
        lead_time_days=lead_time_days,
        rating=sentiment["rating"],
        review_risk_score=sentiment["risk_score"],
        scenario=scenario
    )

    hybrid_score = scoring["hybrid_score"]
    risk_score = scoring["risk_score"]

    if hybrid_score >= 75 and risk_score <= 0.35:
        decision = 'recommended'
    elif hybrid_score >= 55 and risk_score <= 0.6:
        decision = 'caution'
    else:
        decision = 'not_recommended'

    item = PotentialSupplier(
        company_name=company_name,
        website=website or None,
        city=city or None,
        category=category or None,
        source_url=website or None,
        material_query=material_query,
        price=price,
        lead_time_days=lead_time_days,
        rating=sentiment["rating"],
        reviews_count=sentiment["reviews_count"],
        sentiment_score=sentiment["sentiment_score"],
        reliability_score=scoring["reliability_score"],
        risk_score=scoring["risk_score"],
        hybrid_score=scoring["hybrid_score"],
        decision=decision,
        raw_description=reviews_text
    )

    db.session.add(item)
    db.session.commit()

    flash('Новый поставщик оценён по отзывам и коммерческим условиям', 'success')
    return redirect(url_for('admin.potential_suppliers_page'))


@admin_bp.route('/admin/potential-suppliers/<int:item_id>/add-to-suppliers', methods=['POST'])
@role_required('admin')
def add_potential_to_suppliers(item_id):
    item = PotentialSupplier.query.get_or_404(item_id)

    supplier = Supplier(
        company_name=item.company_name,
        address=item.city,
        specialization=item.category,
        rating=item.rating or 3.5,
        delivery_time_days=item.lead_time_days or 1,
        is_active=True
    )

    db.session.add(supplier)
    db.session.flush()

    material = None

    if item.material_query:
        material = Material.query.filter(
            Material.name.ilike(f'%{item.material_query}%')
        ).first()

    if material:
        relation = SupplierMaterial(
            supplier_id=supplier.id,
            material_id=material.id,
            price=item.price,
            lead_time_days=item.lead_time_days,
            is_active=True
        )
        db.session.add(relation)

    item.decision = 'added'
    db.session.commit()

    flash('Поставщик добавлен в основную базу', 'success')
    return redirect(url_for('admin.potential_suppliers_page'))

@admin_bp.route('/admin/potential-suppliers/load-reviews', methods=['POST'])
@role_required('admin')
def load_reviews_for_potential_supplier():
    company_query = request.form.get('reviews_company', '').strip()

    if not company_query:
        return {
            "success": False,
            "error": "Введите название компании"
        }

    try:
        result = parse_reviews_from_company_name(company_query, limit=5)
        return result

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }