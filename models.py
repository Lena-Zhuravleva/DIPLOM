from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    role = db.Column(db.Enum('admin', 'logistician', 'warehouse', 'supplier', 'viewer'), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())
    is_active = db.Column(db.Boolean, default=True)

    supplier = db.relationship('Supplier', backref='user', uselist=False)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Supplier(db.Model):
    __tablename__ = 'suppliers'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True)

    company_name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.Text)
    rating = db.Column(db.Numeric(3, 2), default=5.0)
    delivery_zone = db.Column(db.Enum('local', 'regional', 'international'), default='local')
    specialization = db.Column(db.String(100))
    contact_person = db.Column(db.String(100))
    delivery_time_days = db.Column(db.Integer, default=1)

    materials = db.relationship(
        "Material",
        secondary="supplier_materials",
        backref=db.backref("suppliers", lazy="dynamic"),
        lazy="dynamic"
    )


class Material(db.Model):
    __tablename__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))
    unit = db.Column(db.String(20), nullable=False)
    min_stock_level = db.Column(db.Integer, default=10)
    current_stock = db.Column(db.Integer, default=0)
    status = db.Column(db.Enum('normal', 'warning', 'critical'), default='normal')
    last_updated = db.Column(
        db.TIMESTAMP,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp()
    )

    def update_status(self):
        if self.current_stock <= 0:
            self.status = 'critical'
        elif self.current_stock <= self.min_stock_level:
            self.status = 'warning'
        else:
            self.status = 'normal'


class Delivery(db.Model):
    __tablename__ = 'deliveries'

    id = db.Column(db.Integer, primary_key=True)

    date = db.Column(db.Date, nullable=False, index=True)
    time_slot = db.Column(db.Time, nullable=False)

    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'))

    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Enum('planned', 'in_transit', 'delivered', 'cancelled'), default='planned')
    notes = db.Column(db.Text)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())

    unload_place = db.Column(db.String(20), nullable=True)
    duration_min = db.Column(db.Integer, default=15)

    supplier = db.relationship('Supplier', backref='deliveries')
    material = db.relationship('Material', backref='deliveries')
    creator = db.relationship('User', backref='created_deliveries', foreign_keys=[created_by])


class UnloadingFact(db.Model):
    __tablename__ = 'unloading_facts'

    id = db.Column(db.Integer, primary_key=True)

    date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    duration_min = db.Column(db.Integer, nullable=False, default=15)

    unload_place = db.Column(db.String(20), nullable=False, index=True)

    delivery_id = db.Column(
        db.Integer,
        db.ForeignKey('deliveries.id', ondelete='SET NULL'),
        nullable=True
    )

    status = db.Column(db.Enum('planned', 'in_progress', 'done', 'cancelled'),
                       default='planned', nullable=False)

    notes = db.Column(db.Text)
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())

    delivery = db.relationship('Delivery', backref='unloading_facts')


class Request(db.Model):
    __tablename__ = 'requests'

    id = db.Column(db.Integer, primary_key=True)

    type = db.Column(db.Enum('supplier_booking', 'logistic_order', 'warehouse_order'), nullable=False)

    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), nullable=True)
    quantity = db.Column(db.Integer, nullable=True)

    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=True)

    requested_date = db.Column(db.Date, nullable=True)
    requested_time_slot = db.Column(db.Time, nullable=True)

    unload_place = db.Column(db.String(20), nullable=True)
    duration_min = db.Column(db.Integer, default=15)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    status = db.Column(db.Enum(
        'pending_logistician',
        'pending_supplier',
        'confirmed_supplier',
        'approved',
        'rejected',
        'rejected_supplier',
        'reschedule_requested'
    ), default='pending_logistician')

    notes = db.Column(db.Text)

    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())

    material = db.relationship('Material')
    supplier = db.relationship('Supplier')
    creator = db.relationship('User')

# для плана закупок
class ProcurementPlan(db.Model):
    __tablename__ = 'procurement_plan'

    id = db.Column(db.Integer, primary_key=True)

    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    planned_date = db.Column(db.Date, nullable=False)

    status = db.Column(
        db.Enum('planned', 'in_progress', 'completed'),
        default='planned',
        nullable=False
    )

    notes = db.Column(db.Text)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())
    updated_at = db.Column(
        db.TIMESTAMP,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp()
    )

    material = db.relationship('Material', backref='procurement_plan_items')
    creator = db.relationship('User', backref='created_procurement_plan_items', foreign_keys=[created_by])

# правильная связующая таблица: составной PK
class SupplierMaterial(db.Model):
    __tablename__ = 'supplier_materials'

    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), primary_key=True)

    supplier = db.relationship('Supplier', backref='supplier_materials')
    material = db.relationship('Material', backref='supplier_materials')
