import pymysql
import os
from werkzeug.security import generate_password_hash
from config import Config

def init_database():
    try:
        # Connect to MySQL Server using PyMySQL (pure Python, 3.14 compatible)
        conn = pymysql.connect(
            host=Config.DB_HOST,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            port=Config.DB_PORT
        )
        cursor = conn.cursor()
        
        # Create database (Force rebuild to apply schema migrations)
        cursor.execute(f"DROP DATABASE IF EXISTS {Config.DB_NAME}")
        cursor.execute(f"CREATE DATABASE {Config.DB_NAME}")
        cursor.execute(f"USE {Config.DB_NAME}")
        
        # Create tables
        print("Creating tables...")
        
        # Users
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                role ENUM('student', 'staff', 'department', 'warden', 'principal', 'admin') DEFAULT 'student',
                department VARCHAR(100) DEFAULT NULL,
                profile_photo VARCHAR(255) DEFAULT 'default.png',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        
        # Grievances
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS grievances (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                assigned_to INT DEFAULT NULL,
                staff_id INT DEFAULT NULL,
                warden_id INT DEFAULT NULL,
                is_anonymous BOOLEAN DEFAULT FALSE,
                targets_staff BOOLEAN DEFAULT FALSE,
                targets_warden BOOLEAN DEFAULT FALSE,
                targets_authority BOOLEAN DEFAULT FALSE,
                staff_approved BOOLEAN DEFAULT FALSE,
                warden_resolved BOOLEAN DEFAULT FALSE,
                authority_approved BOOLEAN DEFAULT FALSE,
                title VARCHAR(150) NOT NULL,
                category ENUM('Department', 'Hostel') NOT NULL,
                target_department VARCHAR(100) DEFAULT NULL,
                description TEXT NOT NULL,
                attachment VARCHAR(255) DEFAULT NULL,
                status ENUM('pending', 'staff_review', 'authority_review', 'in_progress', 'in-progress', 'resolved') DEFAULT 'pending',
                priority ENUM('low', 'medium', 'high') DEFAULT 'medium',
                remarks TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (assigned_to) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY (staff_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY (warden_id) REFERENCES users(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        
        # Replies
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS grievance_replies (
                id INT AUTO_INCREMENT PRIMARY KEY,
                grievance_id INT NOT NULL,
                sender_id INT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (grievance_id) REFERENCES grievances(id) ON DELETE CASCADE,
                FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        
        # Notifications
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                message TEXT NOT NULL,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        
        # Password Resets
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS password_resets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(100) NOT NULL,
                token VARCHAR(100) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        
        # Seed users
        print("Seeding initial users for 6 roles...")
        
        admin_pwd = generate_password_hash("Admin@123")
        student_pwd = generate_password_hash("Student@123")
        staff_pwd = generate_password_hash("Staff@123")
        dept_pwd = generate_password_hash("Authority@123")
        warden_pwd = generate_password_hash("Warden@123")
        principal_pwd = generate_password_hash("Principal@123")
        
        # 1. Admin
        cursor.execute(
            "INSERT INTO users (name, email, password, role, department, profile_photo) VALUES (%s, %s, %s, %s, %s, %s)",
            ("System Administrator", "admin@example.com", admin_pwd, "admin", "IT Administration", "admin.png")
        )
        # 2. Student
        cursor.execute(
            "INSERT INTO users (name, email, password, role, department, profile_photo) VALUES (%s, %s, %s, %s, %s, %s)",
            ("Jane Doe (Student)", "student@example.com", student_pwd, "student", "Computer Science", "student.png")
        )
        # 3. Staff
        cursor.execute(
            "INSERT INTO users (name, email, password, role, department, profile_photo) VALUES (%s, %s, %s, %s, %s, %s)",
            ("Department Staff", "staff@example.com", staff_pwd, "staff", "Computer Science", "staff.png")
        )
        # 4. Department Authority (Common)
        cursor.execute(
            "INSERT INTO users (name, email, password, role, department, profile_photo) VALUES (%s, %s, %s, %s, %s, %s)",
            ("Grievance Authority", "authority@example.com", dept_pwd, "department", None, "authority.png")
        )
        # 5. Hostel Warden
        cursor.execute(
            "INSERT INTO users (name, email, password, role, department, profile_photo) VALUES (%s, %s, %s, %s, %s, %s)",
            ("Hostel Warden", "warden@example.com", warden_pwd, "warden", None, "warden.png")
        )
        # 6. Principal
        cursor.execute(
            "INSERT INTO users (name, email, password, role, department, profile_photo) VALUES (%s, %s, %s, %s, %s, %s)",
            ("Principal", "principal@example.com", principal_pwd, "principal", None, "principal.png")
        )
        
        conn.commit()
        print("Successfully seeded database with:")
        print("  - Admin: admin@example.com / Admin@123")
        print("  - Student: student@example.com / Student@123")
        print("  - Staff: staff@example.com / Staff@123")
        print("  - Authority: authority@example.com / Authority@123")
        print("  - Warden: warden@example.com / Warden@123")
        print("  - Principal: principal@example.com / Principal@123")
            
        # Create default avatars for all roles
        uploads_dir = Config.UPLOAD_FOLDER
        os.makedirs(uploads_dir, exist_ok=True)
        
        # Create profile pictures for all roles
        roles_list = ['default.png', 'admin.png', 'student.png', 'staff.png', 'authority.png', 'warden.png', 'principal.png']
        
        print("Creating profile avatar images for all roles...")
        png_bytes = bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000100000500010d0a2db40000000049454e44ae426082')
        
        for role_file in roles_list:
            role_path = os.path.join(uploads_dir, role_file)
            if not os.path.exists(role_path):
                with open(role_path, 'wb') as f:
                    f.write(png_bytes)
        
        print("Profile avatars created for all roles.")

        cursor.close()
        conn.close()
        print("Database initialization completed successfully!")
        
    except Exception as err:
        print(f"Error connecting/initializing: {err}")
        print("\nMake sure MySQL Server is running and check settings in config.py.")

if __name__ == "__main__":
    init_database()
