-- schema.sql
-- MySQL 8+
-- Создание базы и таблиц для Logistic System

DROP DATABASE IF EXISTS logistics_db;
CREATE DATABASE logistics_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE logistics_db;

-- Чтобы корректно работали FK при создании
SET FOREIGN_KEY_CHECKS = 0;

-- ===== users =====
DROP TABLE IF EXISTS users;
CREATE TABLE users (
  id INT PRIMARY KEY AUTO_INCREMENT,
  username VARCHAR(50) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  email VARCHAR(100) UNIQUE NOT NULL,
  role ENUM('admin', 'logistician', 'warehouse', 'supplier', 'viewer') NOT NULL,
  full_name VARCHAR(100) NOT NULL,
  phone VARCHAR(20),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  is_active BOOLEAN DEFAULT TRUE
) ENGINE=InnoDB;

-- ===== suppliers =====
DROP TABLE IF EXISTS suppliers;
CREATE TABLE suppliers (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_id INT UNIQUE,
  company_name VARCHAR(100) NOT NULL,
  address TEXT,
  rating DECIMAL(3,2) DEFAULT 5.0,
  delivery_zone ENUM('local','regional','international') DEFAULT 'local',
  specialization VARCHAR(100),
  contact_person VARCHAR(100),
  delivery_time_days INT DEFAULT 1,
  CONSTRAINT fk_suppliers_user
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ===== materials =====
DROP TABLE IF EXISTS materials;
CREATE TABLE materials (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL,
  category VARCHAR(50),
  unit VARCHAR(20) NOT NULL,
  min_stock_level INT DEFAULT 10,
  current_stock INT DEFAULT 0,
  status ENUM('normal','warning','critical') DEFAULT 'normal',
  last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ===== procurement_plan =====
DROP TABLE IF EXISTS procurement_plan;
CREATE TABLE procurement_plan (
  id INT PRIMARY KEY AUTO_INCREMENT,

  material_id INT NOT NULL,
  quantity INT NOT NULL,
  planned_date DATE NOT NULL,
  status ENUM('planned','in_progress','completed') NOT NULL DEFAULT 'planned',

  notes TEXT,

  created_by INT NOT NULL,

  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  CONSTRAINT fk_procurement_plan_material
    FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,

  CONSTRAINT fk_procurement_plan_created_by
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ===== requests =====
DROP TABLE IF EXISTS requests;
CREATE TABLE requests (
  id INT PRIMARY KEY AUTO_INCREMENT,
  type ENUM('supplier_booking','logistic_order','warehouse_order') NOT NULL,

  material_id INT NULL,
  quantity INT NULL,

  supplier_id INT NULL,

  requested_date DATE NULL,
  requested_time_slot TIME NULL,
  duration_min INT NOT NULL DEFAULT 15,

  -- Место выгрузки (если нужно для календаря по местам)
  unload_place VARCHAR(20) NULL,

  created_by INT NOT NULL,

  status ENUM(
      'pending_logistician',
      'pending_supplier',
      'approved',
      'rejected',
      'rejected_supplier',
      'reschedule_requested'
    ) DEFAULT 'pending_logistician',

  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  CONSTRAINT fk_requests_material
    FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE SET NULL,
  CONSTRAINT fk_requests_supplier
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL,
  CONSTRAINT fk_requests_created_by
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ===== supplier_materials =====
DROP TABLE IF EXISTS supplier_materials;
CREATE TABLE supplier_materials (
  supplier_id INT NOT NULL,
  material_id INT NOT NULL,
  PRIMARY KEY (supplier_id, material_id),

  CONSTRAINT fk_supplier_materials_supplier
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE,

  CONSTRAINT fk_supplier_materials_material
    FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ===== deliveries =====
DROP TABLE IF EXISTS deliveries;
CREATE TABLE deliveries (
  id INT PRIMARY KEY AUTO_INCREMENT,
  date DATE NOT NULL,
  time_slot TIME NOT NULL,
  duration_min INT NOT NULL DEFAULT 15,

  -- Место выгрузки (если нужно)
  unload_place VARCHAR(20) NULL,

  supplier_id INT NULL,
  material_id INT NULL,
  quantity INT NOT NULL,

  status ENUM('planned','in_transit','delivered','cancelled') DEFAULT 'planned',
  notes TEXT,

  created_by INT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  INDEX idx_deliveries_date (date),
  INDEX idx_deliveries_date_time (date, time_slot),

  CONSTRAINT fk_deliveries_supplier
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL,
  CONSTRAINT fk_deliveries_material
    FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE SET NULL,
  CONSTRAINT fk_deliveries_created_by
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ===== unloading_facts (ФАКТ разгрузки) =====
DROP TABLE IF EXISTS unloading_facts;
CREATE TABLE unloading_facts (
  id INT PRIMARY KEY AUTO_INCREMENT,
  date DATE NOT NULL,
  start_time TIME NOT NULL,
  duration_min INT NOT NULL DEFAULT 15,
  unload_place VARCHAR(20) NOT NULL,

  delivery_id INT NULL,

  status ENUM('planned','in_progress','done','cancelled') DEFAULT 'planned',
  notes TEXT,

  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  INDEX idx_unloading_date (date),
  INDEX idx_unloading_place (unload_place),
  INDEX idx_unloading_date_place_time (date, unload_place, start_time),

  CONSTRAINT fk_unloading_delivery
    FOREIGN KEY (delivery_id) REFERENCES deliveries(id) ON DELETE SET NULL
) ENGINE=InnoDB;

SET FOREIGN_KEY_CHECKS = 1;
