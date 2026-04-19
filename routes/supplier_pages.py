from flask import Blueprint, render_template, session
from decorators import role_required
from models import Supplier, SupplierMaterial, Request, Material
from sqlalchemy import desc

supplier_pages_bp = Blueprint('supplier_pages', __name__, url_prefix='/supplier')


def _get_supplier():
    return Supplier.query.filter_by(user_id=session['user_id']).first()


@supplier_pages_bp.get('/dashboard')
@role_required('supplier')
def supplier_dashboard():
    # Можно показать кратко: последние заявки, статус и т.п.
    supplier = _get_supplier()
    last_requests = []
    if supplier:
        last_requests = (Request.query
                         .filter_by(supplier_id=supplier.id)
                         .order_by(desc(Request.created_at))
                         .limit(5).all())
    return render_template('supplier/dashboard.html', last_requests=last_requests)


@supplier_pages_bp.get('/booking')
@role_required('supplier')
def supplier_booking_page():
    # Для выпадающего списка материалов на странице бронирования
    supplier = _get_supplier()
    materials = []
    if supplier:
        rows = SupplierMaterial.query.filter_by(supplier_id=supplier.id).all()
        materials = [r.material for r in rows if r.material]
    return render_template('supplier/booking.html', materials=materials)


@supplier_pages_bp.get('/requests')
@role_required('supplier')
def supplier_requests_page():
    # Можно рендерить сервером или грузить через fetch из API
    return render_template('supplier/requests.html')


@supplier_pages_bp.get('/materials')
@role_required('supplier')
def supplier_materials_page():
    # Можно так же: сервером или через fetch из API
    supplier = _get_supplier()
    materials = []
    if supplier:
        rows = SupplierMaterial.query.filter_by(supplier_id=supplier.id).all()
        materials = [r.material for r in rows if r.material]
    return render_template('supplier/materials.html', materials=materials)
