-- PostgreSQL Database Schema for Student Grievance System

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'student',
    department VARCHAR(100) DEFAULT NULL,
    profile_photo VARCHAR(255) DEFAULT 'default.png',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Grievances Table
CREATE TABLE IF NOT EXISTS grievances (
    id SERIAL PRIMARY KEY,
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
    category VARCHAR(50) NOT NULL,
    target_department VARCHAR(100) DEFAULT NULL,
    description TEXT NOT NULL,
    attachment VARCHAR(255) DEFAULT NULL,
    resolved_evidence VARCHAR(255) DEFAULT NULL,
    student_deleted BOOLEAN DEFAULT FALSE,
    staff_deleted BOOLEAN DEFAULT FALSE,
    warden_deleted BOOLEAN DEFAULT FALSE,
    authority_deleted BOOLEAN DEFAULT FALSE,
    admin_deleted BOOLEAN DEFAULT FALSE,
    principal_deleted BOOLEAN DEFAULT FALSE,
    status VARCHAR(50) DEFAULT 'pending',
    priority VARCHAR(50) DEFAULT 'normal',
    remarks TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (assigned_to) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (staff_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (warden_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Grievance Replies Table
CREATE TABLE IF NOT EXISTS grievance_replies (
    id SERIAL PRIMARY KEY,
    grievance_id INT NOT NULL,
    sender_id INT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (grievance_id) REFERENCES grievances(id) ON DELETE CASCADE,
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Notifications Table
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Password Resets Table
CREATE TABLE IF NOT EXISTS password_resets (
    id SERIAL PRIMARY KEY,
    email VARCHAR(100) NOT NULL,
    token VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
