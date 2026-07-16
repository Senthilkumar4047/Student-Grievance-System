import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'student_grievance_secret_key_987654321_key')
    
    # PostgreSQL / Supabase Database Connection configuration
    DATABASE_URL = os.environ.get('DATABASE_URL')
    
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_USER = os.environ.get('DB_USER', 'postgres')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'postgres')
    DB_NAME = os.environ.get('DB_NAME', 'postgres')
    DB_PORT = int(os.environ.get('DB_PORT', 5432))
    
    # File upload configurations
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB limit
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'zip', 'rar'}
