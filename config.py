import os
class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL', 'mysql+mysqlconnector://root:YUIOPtrewq131079@localhost/logistics_db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
