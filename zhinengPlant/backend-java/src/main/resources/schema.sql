-- ============================================================
-- 绿植智能养护系统 · MySQL 建表脚本（对齐需求文档 12 张表）
-- 启动时仅创建不存在的表，保留已有用户和业务数据
-- ============================================================
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS users (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    phone         VARCHAR(20) UNIQUE,
    password_hash VARCHAR(128) NOT NULL,
    nickname      VARCHAR(50) DEFAULT '绿植主人',
    openid        VARCHAR(64) UNIQUE,
    family_id     BIGINT DEFAULT 0,
    role          VARCHAR(20) DEFAULT 'owner',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 用户扩展资料与登录账号分表保存，后续可继续扩展个性签名等字段
CREATE TABLE IF NOT EXISTS user_profile (
    user_id     BIGINT PRIMARY KEY,
    avatar_url  VARCHAR(255),
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS family_groups (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(50) NOT NULL,
    owner_id    BIGINT NOT NULL,
    invite_code VARCHAR(32) UNIQUE,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS family_members (
    id        BIGINT AUTO_INCREMENT PRIMARY KEY,
    family_id BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    role      VARCHAR(20) DEFAULT 'member',
    duty      VARCHAR(50)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS plant_species (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(50) NOT NULL,
    latin_name   VARCHAR(80),
    env_snapshot TEXT,               -- JSON：光照/温度/湿度/浇水间隔
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS plant_profile (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id             BIGINT NOT NULL,
    species_id          BIGINT NOT NULL,
    name                VARCHAR(50) NOT NULL,
    pot_material        VARCHAR(20),
    init_height_cm      DECIMAL(5,1),
    emotion_tag         VARCHAR(50),
    status              VARCHAR(20) DEFAULT 'ok',
    last_water_at       DATETIME,
    water_interval_days INT DEFAULT 3,
    photo_url           VARCHAR(255),
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS care_record (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    plant_id   BIGINT NOT NULL,
    user_id    BIGINT,
    type       VARCHAR(20) NOT NULL,   -- water/fertilize/prune/repot/other
    note       VARCHAR(200),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS growth_metric (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    plant_id    BIGINT NOT NULL,
    height_cm   DECIMAL(5,1),
    leaf_count  INT,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS diagnosis_record (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    plant_id   BIGINT DEFAULT 0,
    user_id    BIGINT NOT NULL,
    symptoms   TEXT,               -- JSON 症状多标签
    report     TEXT,               -- JSON 诊断报告
    feedback   TINYINT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS knowledge_content (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    species_id BIGINT NOT NULL,
    habit      TEXT,
    seasons    TEXT,               -- 分号分隔
    water      TEXT,
    fertilize  TEXT,
    breed      TEXT,
    faq        TEXT                -- JSON
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS care_plan_item (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    plant_id   BIGINT NOT NULL,
    task_type  VARCHAR(20) NOT NULL,
    due_date   DATE,
    done       TINYINT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS notification (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    title      VARCHAR(100),
    is_read    TINYINT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS family_task (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    family_id   BIGINT NOT NULL,
    plant_id    BIGINT,
    title       VARCHAR(100),
    assignee_id BIGINT,
    due         DATE,
    done        TINYINT DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
