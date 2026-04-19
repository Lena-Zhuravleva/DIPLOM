from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from extensions import db
from models import User, Supplier
from decorators import role_required

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username, is_active=True).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['full_name'] = user.full_name

            flash(f'Добро пожаловать, {user.full_name}!', 'success')
            return redirect(url_for('dashboard.dashboard'))

        flash('Неверный логин или пароль', 'error')

    return render_template('base/login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('dashboard.home'))
