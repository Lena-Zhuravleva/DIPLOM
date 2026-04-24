import datetime
from flask import Blueprint, render_template, session, redirect, url_for
from decorators import login_required
from models import User, Material, Delivery, Supplier

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def home():
    return render_template('base/index.html')


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    role = session.get('role')

    materials = Material.query.all()
    user = User.query.get(session['user_id'])

    context = {
        'materials': materials,
        'user': user
    }

    if role == 'admin':
        users = User.query.all()
        suppliers = Supplier.query.order_by(Supplier.company_name.asc()).all()
        context.update({'users': users, 'suppliers': suppliers})
        return render_template('admin/dashboard.html', **context)

    if role == 'logistician':
        return redirect(url_for('logistician_pages.logistician_dashboard'))

    if role == 'warehouse':
        today = datetime.date.today()
        todays_deliveries = Delivery.query.filter_by(date=today).order_by(Delivery.time_slot.asc()).all()

        low_stock_materials = Material.query.filter(Material.current_stock <= Material.min_stock_level).all()

        context.update({
            'low_stock_materials': low_stock_materials,
            'todays_deliveries': todays_deliveries
        })

        return render_template('warehouse/dashboard.html', **context)

    if role == 'supplier':
        supplier = Supplier.query.filter_by(user_id=session['user_id']).first()
        materials = Material.query.order_by(Material.name.asc()).all()

        context.update({
            'supplier': supplier,
            'materials': materials
        })

        return render_template('supplier/dashboard.html', **context)

    return render_template('viewer/dashboard.html', **context)
