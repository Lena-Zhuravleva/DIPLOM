from flask import Blueprint, jsonify, request
from decorators import login_required, role_required
from extensions import db
from models import Material

api_materials_bp = Blueprint('api_materials', __name__)


@api_materials_bp.route('/api/materials')
@login_required
def get_materials():
    materials = Material.query.all()
    return jsonify([{
        'id': m.id,
        'name': m.name,
        'category': m.category,
        'unit': m.unit,
        'current_stock': m.current_stock,
        'min_stock_level': m.min_stock_level,
        'status': m.status
    } for m in materials])


@api_materials_bp.route('/api/update_stock/<int:material_id>', methods=['POST'])
@role_required('warehouse', 'admin')
def update_stock(material_id):
    material = Material.query.get_or_404(material_id)
    new_stock = (request.json or {}).get('stock')

    if new_stock is None:
        return jsonify({'success': False, 'error': 'Не указан запас'}), 400

    material.current_stock = int(new_stock)
    material.update_status()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Запас обновлен',
        'material': {
            'id': material.id,
            'name': material.name,
            'current_stock': material.current_stock,
            'status': material.status
        }
    })
