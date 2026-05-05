-- ══════════════════════════════════════════════
-- FRAS Database Schema — Full Version
-- Run once: mysql -u root -p smart_attendance < schema.sql
-- ══════════════════════════════════════════════

CREATE DATABASE IF NOT EXISTS smart_attendance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE smart_attendance;

-- ── Super Admin ──────────────────────────────
CREATE TABLE IF NOT EXISTS super_admin (
    id       INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(60)  NOT NULL UNIQUE,
    password VARCHAR(120) NOT NULL
);

-- ── Private Sites/Classes (admin-owned) ──────
CREATE TABLE IF NOT EXISTS organizations (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    org_name         VARCHAR(120) NOT NULL,
    room_type        VARCHAR(60)  DEFAULT 'Classroom',
    venue_number     VARCHAR(80)  DEFAULT NULL,
    cabin_number     VARCHAR(80)  DEFAULT NULL,
    admin_user       VARCHAR(80),
    admin_password   VARCHAR(120),
    capacity         INT          DEFAULT 0,
    admin_logged_today DATE       DEFAULT NULL,
    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- ── Public Venues (super admin creates, no fixed admin) ──
CREATE TABLE IF NOT EXISTS public_venues (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    venue_name       VARCHAR(120) NOT NULL,
    venue_type       VARCHAR(60)  DEFAULT 'Hall',
    venue_number     VARCHAR(80)  DEFAULT NULL,
    capacity         INT          DEFAULT 0,
    status           ENUM('available','occupied') DEFAULT 'available',
    current_booker   VARCHAR(120) DEFAULT NULL,
    booked_org_id    INT          DEFAULT NULL,
    booked_from      DATETIME     DEFAULT NULL,
    booked_until     DATETIME     DEFAULT NULL,
    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- ── Public Venue Booking Requests ────────────
CREATE TABLE IF NOT EXISTS venue_requests (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    venue_id       INT          NOT NULL,
    org_id         INT          NOT NULL,
    admin_name     VARCHAR(120) NOT NULL,
    purpose        VARCHAR(255) DEFAULT NULL,
    booking_date   DATE         NOT NULL,
    start_time     TIME         NOT NULL,
    end_time       TIME         NOT NULL,
    status         ENUM('pending','approved','denied') DEFAULT 'pending',
    requested_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    reviewed_at    TIMESTAMP    DEFAULT NULL,
    FOREIGN KEY (venue_id) REFERENCES public_venues(id) ON DELETE CASCADE,
    FOREIGN KEY (org_id)   REFERENCES organizations(id)  ON DELETE CASCADE
);

-- ── Students ──────────────────────────────────
CREATE TABLE IF NOT EXISTS students (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    org_id        INT          NOT NULL,
    name          VARCHAR(120) NOT NULL,
    roll_number   VARCHAR(60)  NOT NULL UNIQUE,
    age           INT          DEFAULT 0,
    class_name    VARCHAR(80)  DEFAULT 'N/A',
    face_encoding LONGTEXT,
    registered_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
);

-- ── Attendance ────────────────────────────────
CREATE TABLE IF NOT EXISTS attendance (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT  NOT NULL,
    date       DATE NOT NULL,
    time       TIME NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

-- ── Seed Super Admin ─────────────────────────
INSERT IGNORE INTO super_admin (username, password) VALUES ('superadmin', 'super123');
