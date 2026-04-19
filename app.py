from flask import Flask, redirect, url_for, render_template
from config import Config
from extensions import db
import models

from routes.auth import auth_bp
from routes.materials import materials_bp
from routes.suppliers import suppliers_bp
from routes.api_supplier import api_supplier_bp
from routes.dashboard import dashboard_bp
from routes.admin import admin_bp
from routes.api_materials import api_materials_bp
from routes.api_logistician import api_logistician_bp
from routes.supplier_pages import supplier_pages_bp
from routes.logistician_pages import logistician_pages_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(suppliers_bp)
    app.register_blueprint(api_supplier_bp)
    app.register_blueprint(materials_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_materials_bp)
    app.register_blueprint(api_logistician_bp)
    app.register_blueprint(supplier_pages_bp)
    app.register_blueprint(logistician_pages_bp)

    return app


app = create_app()

@app.route('/login', methods=['GET', 'POST'])
def login():
    return redirect(url_for('auth.login'))

@app.route('/logout')
def logout():
    return redirect(url_for('auth.logout'))

@app.route('/about')
def about():
    return render_template('base/about.html')

@app.route('/features')
def features():
    return render_template('base/features.html')

@app.route('/dashboard')
def dashboard():
    return redirect(url_for('dashboard.dashboard'))
if __name__ == '__main__':
    app.run(debug=True, port=5000)

