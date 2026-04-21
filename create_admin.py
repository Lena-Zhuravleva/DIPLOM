from app import app
from extensions import db
from models import User

with app.app_context():
    existing = User.query.filter_by(username="admin").first()
    if existing:
        print("Админ уже существует")
    else:
        user = User(
            username="admin",
            email="admin",
            role="admin",
            full_name="Admin"
        )
        user.set_password("123")

        db.session.add(user)
        db.session.commit()

        print("Админ создан!")