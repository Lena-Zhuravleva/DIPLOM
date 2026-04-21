from flask import Blueprint, render_template, session, redirect, url_for
from decorators import role_required
from models import Supplier, SupplierMaterial, Request
from sqlalchemy import desc

supplier_pages_bp = Blueprint('supplier_pages', __name__, url_prefix='/supplier')


def _get_supplier():
    return Supplier.query.filter_by(user_id=session['user_id']).first()


@supplier_pages_bp.get('/dashboard')
@role_required('supplier')
def supplier_dashboard():
    return redirect(url_for('supplier_pages.supplier_requests_page'))

@supplier_pages_bp.get('/requests')
@role_required('supplier')
def supplier_requests_page():
    return render_template('supplier/requests.html')


@supplier_pages_bp.get('/materials')
@role_required('supplier')
def supplier_materials_page():
    supplier = _get_supplier()
    materials = []
    if supplier:
        rows = SupplierMaterial.query.filter_by(supplier_id=supplier.id).all()
        materials = [r.material for r in rows if r.material]
    return render_template('supplier/materials.html', materials=materials)