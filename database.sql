-- Create Database
CREATE DATABASE IF NOT EXISTS student_grievance;
USE student_grievance;

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    role ENUM('student', 'department', 'warden', 'principal', 'admin') DEFAULT 'student',
    department VARCHAR(100) DEFAULT NULL,
    profile_photo VARCHAR(255) DEFAULT 'default.png',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Grievances Table
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

-- Grievance Replies Table
CREATE TABLE IF NOT EXISTS grievance_replies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    grievance_id INT NOT NULL,
    sender_id INT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (grievance_id) REFERENCES grievances(id) ON DELETE CASCADE,
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Notifications Table
CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Password Resets Table
CREATE TABLE IF NOT EXISTS password_resets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(100) NOT NULL,
    token VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
