from flask import Blueprint, request, redirect, url_for, flash, render_template
from decorators import role_required
from extensions import db
from models import Supplier, SupplierMaterial, User

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
