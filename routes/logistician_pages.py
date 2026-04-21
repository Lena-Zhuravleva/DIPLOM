from flask import Blueprint, render_template
from decorators import role_required
from models import Material, Delivery, ProcurementPlan, Request
import datetime

logistician_pages_bp = Blueprint('logistician_pages', __name__, url_prefix='/logistician')



@logistician_pages_bp.route('/dashboard')
@role_required('logistician')
def logistician_dashboard():
    today = datetime.date.today()
    next_week = today + datetime.timedelta(days=7)

    critical_count = Material.query.filter(
        Material.status.in_(['warning', 'critical'])
    ).count()

    pending_count = Request.query.filter_by(
        status='pending_logistician'
    ).count()

    upcoming_deliveries = Delivery.query.filter(
        Delivery.date >= today,
        Delivery.date <= next_week
    ).order_by(Delivery.date.asc(), Delivery.time_slot.asc()).all()

    return render_template(
        'logistician/dashboard.html',
        critical_count=critical_count,
        pending_count=pending_count,
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

@logistician_pages_bp.route('/procurement-plan')
@role_required('logistician')
def logistician_procurement_plan_page():
    items = ProcurementPlan.query.order_by(ProcurementPlan.planned_date.asc()).all()
    return render_template('logistician/procurement_plan.html', items=items)