from flask import Blueprint, render_template, request, flash
from extensions import db
from models import Material
from decorators import role_required

materials_bp = Blueprint('materials', __name__)

@materials_bp.route('/materials', methods=['GET', 'POST'])
@role_required('admin')
def materials():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category = request.form.get('category', '').strip() or None
        unit = request.form.get('unit', '').strip()
        min_stock_level = request.form.get('min_stock_level', '').strip()
        current_stock = request.form.get('current_stock', '').strip()
        status = request.form.get('status', 'normal').strip()

        if not all([name, unit, min_stock_level, current_stock]):
            flash('Все обязательные поля должны быть заполнены', 'error')
        elif Material.query.filter_by(name=name).first():
            flash('Материал уже существует', 'error')
        else:
            try:
                new_material = Material(
                    name=name,
                    category=category,
                    unit=unit,
                    min_stock_level=int(min_stock_level),
                    current_stock=int(current_stock),
                )
                new_material.update_status()  #пересчитать статус по запасу
                db.session.add(new_material)
                db.session.commit()
                flash(f'Материал "{name}" успешно добавлен!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Ошибка при добавлении материала: {str(e)}', 'error')

    materials = Material.query.order_by(Material.name.asc()).all()
    return render_template('admin/materials.html', materials=materials)
