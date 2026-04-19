from flask import Blueprint, render_template
from decorators import role_required
from models import Material, Delivery
import datetime

logistician_pages_bp = Blueprint('logistician_pages', __name__, url_prefix='/logistician')


@logistician_pages_bp.get('/dashboard')
@role_required('logistician')
def logi_dashboard():
    # лёгкий обзор: проблемные материалы + ближайшие поставки (если нужно)
    critical_materials = Material.query.filter(Material.status.in_(['warning', 'critical'])).all()

    today = datetime.date.today()
    in_7 = today + datetime.timedelta(days=7)
    upcoming_deliveries = Delivery.query.filter(
        Delivery.date >= today,
        Delivery.date <= in_7
    ).all()

    return render_template(
        'logistician/dashboard.html',
        critical_materials=critical_materials,
        upcoming_deliveries=upcoming_deliveries
    )


@logistician_pages_bp.get('/calendar')
@role_required('logistician')
def logi_calendar_page():
    return render_template('logistician/calendar.html')


@logistician_pages_bp.get('/requests')
@role_required('logistician')
def logi_requests_page():
    return render_template('logistician/requests.html')


@logistician_pages_bp.get('/materials')
@role_required('logistician')
def logi_materials_page():
    critical_materials = Material.query.filter(Material.status.in_(['warning', 'critical'])).all()
    return render_template('logistician/materials.html', critical_materials=critical_materials)
