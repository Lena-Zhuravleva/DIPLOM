from flask import Blueprint, render_template
from decorators import role_required
from models import Supplier, Material

suppliers_bp = Blueprint('suppliers', __name__)

@suppliers_bp.route('/suppliers', methods=['GET'])
@role_required('admin')
def suppliers_page():
    suppliers = Supplier.query.order_by(Supplier.company_name.asc()).all()
    materials = Material.query.order_by(Material.name.asc()).all()
    return render_template('admin/suppliers.html', suppliers=suppliers, materials=materials)
