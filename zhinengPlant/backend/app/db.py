"""
db.py —— SQLite 数据库初始化与基础访问
- 开发期用 SQLite（零安装，文件即库）；部署/答辩前可平滑切到 MySQL（见 README）
- 所有 SQL 均使用参数化查询，防止注入
- 12 张核心表：users / family_groups / family_members / plant_species /
  plant_profile / care_record / growth_metric / diagnosis_record /
  knowledge_content / care_plan_item / notification / family_task
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "greenplant.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT UNIQUE,
  password_hash TEXT,
  nickname TEXT,
  openid TEXT UNIQUE,
  family_id INTEGER DEFAULT 0,
  role TEXT DEFAULT 'owner',
  created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS family_groups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT,
  owner_id INTEGER,
  invite_code TEXT,
  created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS family_members (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  family_id INTEGER,
  user_id INTEGER,
  role TEXT DEFAULT 'member',
  duty TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS plant_species (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE,
  genus TEXT,
  env_snapshot TEXT,
  created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS plant_profile (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  family_id INTEGER,
  user_id INTEGER,
  species_id INTEGER,
  name TEXT,
  purchase_date TEXT,
  pot_material TEXT,
  init_height_cm REAL,
  emotion_tag TEXT,
  photo_url TEXT,
  height_cm REAL DEFAULT 0,
  water_interval_days INTEGER DEFAULT 7,
  last_water_at TEXT,
  status TEXT DEFAULT 'ok',
  archived INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS care_record (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plant_id INTEGER,
  user_id INTEGER,
  type TEXT,
  amount TEXT,
  note TEXT,
  photo_url TEXT,
  created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS growth_metric (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plant_id INTEGER,
  height_cm REAL,
  measured_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS diagnosis_record (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plant_id INTEGER,
  user_id INTEGER,
  image_url TEXT,
  symptoms TEXT,
  report TEXT,
  feedback INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS knowledge_content (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  species_id INTEGER,
  habit TEXT, seasons TEXT, water TEXT, fertilize TEXT, breed TEXT, faq TEXT
);
CREATE TABLE IF NOT EXISTS care_plan_item (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plant_id INTEGER,
  task_type TEXT,
  due_date TEXT,
  done INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS notification (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  title TEXT,
  is_read INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS family_task (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  family_id INTEGER,
  plant_id INTEGER,
  title TEXT,
  assignee_id INTEGER,
  due TEXT,
  done INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now','localtime'))
);
"""

# 内置知识库种子（species_id 1-6：绿萝/龟背竹/虎皮兰/多肉/发财树/兰花）
SEED_SPECIES = [
    ("绿萝", "天南星科",
     '{"temp":"16~28℃","humidity":"65%","light":"半阴","waterInterval":"3~5天"}'),
    ("龟背竹", "天南星科",
     '{"temp":"18~28℃","humidity":"60%","light":"散射光","waterInterval":"5~7天"}'),
    ("虎皮兰", "天门冬科",
     '{"temp":"15~30℃","humidity":"40%","light":"耐阴","waterInterval":"10~14天"}'),
    ("多肉植物", "景天科",
     '{"temp":"15~25℃","humidity":"40%","light":"全日照","waterInterval":"7~10天"}'),
    ("发财树", "木棉科",
     '{"temp":"20~30℃","humidity":"55%","light":"散射光","waterInterval":"7~10天"}'),
    ("兰花", "兰科",
     '{"temp":"18~28℃","humidity":"70%","light":"散射光","waterInterval":"5~7天"}'),
]

SEED_KNOWLEDGE = [
    (1, "喜温暖湿润，耐半阴，怕强光直射。",
     "春:生长期保持湿润;夏:多喷雾增湿;秋:减少浇水;冬:控水防冻",
     "表土干透再浇透，约3~5天一次。",
     "生长季每月1~2次稀薄液肥。",
     "春秋剪取带气生根的茎段扦插。",
     '[{"q":"叶子发黄怎么办","a":"多为浇水过多或光照不足"},{"q":"可以水培吗","a":"可以，水培需定期换水"}]'),
    (2, "喜温暖湿润和半阴环境，忌强光直射，适宜温度18~28℃。",
     "春:生长期保持湿润;夏:多喷雾增湿;秋:减少浇水;冬:控水防冻",
     "表土下2cm干了再浇透，约5~7天一次，冬季拉长。",
     "生长季每月1~2次稀薄液肥，冬季停肥。",
     "春季换盆时分株，或扦插茎段。",
     '[{"q":"叶子不开裂怎么办","a":"多为光照不足或苗龄偏小，增加散射光"},{"q":"叶尖发黑","a":"多为积水烂根或空气过干，先控水并检查根系"}]'),
    (3, "耐旱耐阴，忌积水，室内极好养活。",
     "春:半月一浇;夏:10天一次;秋:半月一浇;冬:一个月一次",
     "土壤完全干透再浇，宁干勿湿。",
     "生长季每季度一次缓释肥。",
     "分株繁殖，切侧芽晾干后栽种。",
     '[{"q":"多久浇一次水","a":"通常10~14天，看土干透再浇"},{"q":"叶子发软","a":"多为烂根，检查盆土是否积水"}]'),
    (4, "喜阳光充足、干燥环境，怕水涝。",
     "春:见干见湿;夏:遮午晒;秋:控水;冬:断水防冻",
     "盆土干透再浇，冬季几乎不浇。",
     "春秋生长期薄肥勤施。",
     "叶插或分株繁殖。",
     '[{"q":"徒长怎么办","a":"增加光照并控水"},{"q":"叶片化水","a":"浇水过多，停止浇水并通风"}]'),
    (5, "喜高温高湿，怕积水，散射光养护。",
     "春:保持湿润;夏:多喷雾;秋:见干见湿;冬:控水",
     "盆土干透再浇透，宁干勿湿。",
     "生长季每月一次复合肥。",
     "扦插繁殖。",
     '[{"q":"叶尖干枯","a":"空气过干或浇水不足，增加喷雾"},{"q":"掉叶","a":"多为浇水过多或受冻"}]'),
    (6, "喜阴凉湿润，要求通风好、植料透气。",
     "春:保持湿润;夏:遮光通风;秋:减少浇水;冬:控水",
     "植料微润即可，见干见湿。",
     "花期前后施兰花专用肥。",
     "分株繁殖，注意消毒。",
     '[{"q":"为什么不开花","a":"光照不足或温差不够"},{"q":"烂根","a":"植料积水，换透气植料"}]'),
]


def get_conn():
    """每次请求打开新连接（SQLite 线程安全考虑）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        # 种子：品种与知识库（幂等）
        for sp in SEED_SPECIES:
            conn.execute("INSERT OR IGNORE INTO plant_species (name, genus, env_snapshot) VALUES (?,?,?)", sp)
        for k in SEED_KNOWLEDGE:
            conn.execute(
                "INSERT OR IGNORE INTO knowledge_content "
                "(species_id, habit, seasons, water, fertilize, breed, faq) VALUES (?,?,?,?,?,?,?)", k)
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row):
    return dict(row) if row else None


init_db()
