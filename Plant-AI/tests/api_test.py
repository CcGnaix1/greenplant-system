"""接口功能测试 —— 覆盖小程序端的正向流程与异常/边界用例。

只用 Python 标准库（urllib），不依赖 requests，避免为跑测试去动 venv 的依赖。
前置条件：MySQL(3306) + FastAPI 推理服务(5000) + Spring Boot(8000) 三个服务都已启动。

用法：
    C:/Plant/plant-ai/venv/Scripts/python.exe tests/api_test.py

注意：部分用例是**写操作**（建档 / 加记录 / 浇水 / 建任务 / 生成诊断报告 / 标记已读），
会真实改动 plant_db 的数据 —— 这是功能测试的必要代价。用例顺序有讲究：
先跑查询、后跑写入，且把「全部已读」放到通知类用例最后，否则会影响未读数断言。
"""

import csv
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path
from urllib import error, request

BASE = "http://127.0.0.1:8000/api"      # Spring Boot，context-path=/api
AI = "http://127.0.0.1:5000"            # FastAPI 推理服务
SAMPLE_IMG = Path("C:/Plant/upload/recognize/1790591866530.jpg")
DATASET_DIR = Path("C:/Plant/plant-ai/data/plants/绿萝")
RESULT_DIR = Path(__file__).resolve().parent / "results"
DEMO_ARCHIVE_ID = 1                      # seed.sql 里的演示档案，属主 user_id=1

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CTX = {}   # 用例之间传递新建实体的 id
CASES = []


def case(cid, module, title, fn):
    CASES.append(dict(cid=cid, module=module, title=title, fn=fn))


# ---------------- HTTP 基础 ----------------

def _send(method, url, data=None, headers=None, timeout=30):
    req = request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except error.HTTPError as e:
        return e.code, e.read()


def get(path, headers=None):
    return _send("GET", BASE + path, headers=headers)


def post_json(path, body):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    return _send("POST", BASE + path, data=data,
                 headers={"Content-Type": "application/json; charset=utf-8"})


def post_json_ai(path, body):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    return _send("POST", AI + path, data=data,
                 headers={"Content-Type": "application/json; charset=utf-8"})


def build_multipart(field, filename, content, ctype="image/jpeg"):
    boundary = "----planttest" + os.urandom(8).hex()
    body = f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode()
    body += f"Content-Type: {ctype}\r\n\r\n".encode()
    body += content + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def post_file(path, field, filename, content, ctype="image/jpeg"):
    body, ct = build_multipart(field, filename, content, ctype)
    return _send("POST", BASE + path, data=body, headers={"Content-Type": ct}, timeout=60)


def parse(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def ok_code(body, code=0):
    return isinstance(body, dict) and body.get("code") == code


# ================= 植物档案 =================

def t_list():
    s, raw = get("/plant/list")
    b = parse(raw)
    n = len(b["data"]) if ok_code(b) else -1
    return s == 200 and ok_code(b) and n >= 1, f"http={s} code={b.get('code') if b else None} 档案数={n}"


case("TC-P01", "植物档案", "GET /plant/list 返回当前用户档案列表", t_list)


def t_detail_ok():
    s, raw = get("/plant/detail?id=1")
    b = parse(raw)
    d = b.get("data") or {}
    return (s == 200 and ok_code(b) and d.get("name") == "龟背竹",
            f"http={s} 品种={d.get('species')} 高度={d.get('heightCm')}")


case("TC-P02", "植物档案", "GET /plant/detail?id=1 返回龟背竹详情", t_detail_ok)


def t_detail_404():
    s, raw = get("/plant/detail?id=999999")
    b = parse(raw)
    return s == 200 and ok_code(b, 4040), f"http={s} code={b.get('code') if b else None} msg={b.get('msg') if b else None}"


case("TC-P03", "植物档案", "GET /plant/detail?id=999999 档案不存在 → 4040", t_detail_404)


def t_detail_noid():
    s, raw = get("/plant/detail")
    b = parse(raw)
    return s == 200 and ok_code(b, 4001), f"http={s} code={b.get('code') if b else None} msg={b.get('msg') if b else None}（缺必填参数，应报 4001 参数错误）"


case("TC-P04", "植物档案", "GET /plant/detail 缺 id → 应为参数错误 4001", t_detail_noid)


def t_records():
    s, raw = get("/plant/records?id=1")
    b = parse(raw)
    n = len(b["data"]) if ok_code(b) else -1
    return s == 200 and ok_code(b) and n >= 1, f"http={s} 记录数={n}"


case("TC-P05", "植物档案", "GET /plant/records?id=1 返回养护记录", t_records)


def t_records_none():
    s, raw = get("/plant/records?id=999999")
    b = parse(raw)
    return s == 200 and ok_code(b) and b["data"] == [], f"http={s} code={b.get('code') if b else None} 返回空数组（不存在的档案不报错）"


case("TC-P06", "植物档案", "GET /plant/records?id=999999 无记录返回空数组", t_records_none)


def t_create():
    s, raw = post_json("/plant/create", {"name": "自动化测试植株", "species": "绿萝", "location": "测试位"})
    b = parse(raw)
    d = b.get("data") or {}
    if d.get("id"):
        CTX["new_archive_id"] = d["id"]
    return (s == 200 and ok_code(b) and d.get("species") == "绿萝",
            f"http={s} 新档案 id={d.get('id')} 品种={d.get('species')}")


case("TC-P07", "植物档案", "POST /plant/create 按品种名建档（species=绿萝）", t_create)


def t_create_empty():
    s, raw = post_json("/plant/create", {})
    b = parse(raw)
    d = b.get("data") or {}
    return s == 200 and ok_code(b) and d.get("name") == "新植物", f"http={s} 名称默认={d.get('name')} id={d.get('id')}"


case("TC-P08", "植物档案", "POST /plant/create 空对象 → 名称回落「新植物」", t_create_empty)


def t_record():
    s, raw = post_json("/plant/record", {"id": DEMO_ARCHIVE_ID, "type": "浇水", "note": "自动化测试记录"})
    b = parse(raw)
    return s == 200 and ok_code(b), f"http={s} code={b.get('code') if b else None} 新记录={(b.get('data') or {}).get('id')}"


case("TC-P09", "植物档案", "POST /plant/record 添加养护记录", t_record)


def t_record_noid():
    s, raw = post_json("/plant/record", {"note": "缺 id"})
    b = parse(raw)
    return s == 200 and ok_code(b, 4001), f"http={s} code={b.get('code') if b else None} msg={b.get('msg') if b else None}"


case("TC-P10", "植物档案", "POST /plant/record 缺 id → 4001", t_record_noid)


def t_watering():
    s, raw = post_json("/plant/watering", {"id": DEMO_ARCHIVE_ID})
    b = parse(raw)
    d = b.get("data") or {}
    return s == 200 and ok_code(b) and d.get("nextDueDate"), f"http={s} 下次浇水={d.get('nextDueDate')} dryDays={d.get('dryDays')}"


case("TC-P11", "植物档案", "POST /plant/watering 一键浇水", t_watering)


def t_watering_noid():
    s, raw = post_json("/plant/watering", {})
    b = parse(raw)
    return s == 200 and ok_code(b, 4001), f"http={s} code={b.get('code') if b else None}"


case("TC-P12", "植物档案", "POST /plant/watering 缺 id → 4001", t_watering_noid)


# ================= 品种识别 =================

def t_health():
    s, raw = _send("GET", AI + "/health")
    b = parse(raw)
    return (s == 200 and b.get("isMock") is False and b.get("labelsCount") == 20,
            f"http={s} isMock={b.get('isMock')} 类别数={b.get('labelsCount')}")


case("TC-S01", "品种识别", "GET :5000/health 推理服务就绪且非 mock", t_health)


def t_recognize():
    s, raw = post_file("/species/recognize", "image", "test.jpg", SAMPLE_IMG.read_bytes())
    b = parse(raw)
    d = b.get("data") or {}
    cands = d.get("candidates") or []
    top = cands[0] if cands else {}
    good = s == 200 and ok_code(b) and d.get("isMock") is False and top.get("confidence", 0) > 0.5
    return good, f"http={s} isMock={d.get('isMock')} 首选={top.get('species')} 置信度={top.get('confidence')} 候选数={len(cands)}"


case("TC-S02", "品种识别", "POST /species/recognize 上传真图 → 真实推理", t_recognize)


def post_no_part(path):
    """发一个不含任何部件的 multipart，模拟前端根本没带 image 字段。"""
    boundary = "----planttest" + os.urandom(8).hex()
    body = f"--{boundary}--\r\n".encode()
    return _send("POST", BASE + path, data=body,
                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})


def t_recognize_nofile():
    s, raw = post_no_part("/species/recognize")
    b = parse(raw)
    return s == 200 and ok_code(b, 4001), f"http={s} code={b.get('code') if b else None} msg={b.get('msg') if b else None}（缺 image 部件，应报 4001）"


case("TC-S03", "品种识别", "POST /species/recognize 未带 image 部件 → 应为 4001", t_recognize_nofile)


def t_recognize_fake():
    s, raw = post_file("/species/recognize", "image", "fake.jpg", b"this is not an image" * 10)
    b = parse(raw)
    d = b.get("data") or {}
    return s == 200 and ok_code(b) and d.get("isMock") is True, f"http={s} isMock={d.get('isMock')}（非图片 → 回退 mock）"


case("TC-S04", "品种识别", "POST /species/recognize 传非图片 → 回退 mock 不中断", t_recognize_fake)


def t_recognize_emptyfile():
    s, raw = post_file("/species/recognize", "image", "empty.jpg", b"")
    b = parse(raw)
    d = b.get("data") or {}
    top = (d.get("candidates") or [{}])[0]
    return s == 200 and ok_code(b, 4001), (f"http={s} code={b.get('code') if b else None} isMock={d.get('isMock')} "
                                           f"首选={top.get('species')} 置信度={d.get('confidence')}（空文件应报「请选择图片」）")


case("TC-S09", "品种识别", "POST /species/recognize 空文件 → 应报参数错误", t_recognize_emptyfile)


def t_recognize_fake_endpoint_gone():
    s, raw = get("/species/recognize")
    b = parse(raw)
    return not ok_code(b), f"http={s} code={b.get('code') if b else None}（写死数据的 GET 版本已移除，只保留 POST）"


case("TC-S05", "品种识别", "GET /species/recognize 已移除（回归守卫）", t_recognize_fake_endpoint_gone)


def t_ai_outside():
    f = sorted(os.listdir(DATASET_DIR))[0]
    p = str(DATASET_DIR / f).replace("\\", "/")
    s, raw = post_json_ai("/recognize", {"image_path": p, "top_k": 3})
    return s == 403, f"http={s}（越出 C:/Plant/upload 被拒 → 防任意文件读取）"


case("TC-S06", "品种识别", "POST :5000/recognize 数据集路径 → 403 守卫", t_ai_outside)


def t_ai_missing():
    s, raw = post_json_ai("/recognize", {"image_path": "C:/Plant/upload/recognize/__not_exist__.jpg", "top_k": 3})
    return s == 404, f"http={s}"


case("TC-S07", "品种识别", "POST :5000/recognize 文件不存在 → 404", t_ai_missing)


def t_ai_ok():
    s, raw = post_json_ai("/recognize", {"image_path": str(SAMPLE_IMG).replace("\\", "/"), "top_k": 3})
    b = parse(raw)
    top = (b.get("candidates") or [{}])[0]
    return s == 200 and b.get("success") is True and b.get("is_mock") is False, f"http={s} success={b.get('success')} 首选={top.get('species')} 置信度={top.get('confidence')}"


case("TC-S08", "品种识别", "POST :5000/recognize 合法上传路径 → 真实推理", t_ai_ok)


# ================= 症状诊断 =================

def t_symptom():
    s, raw = get("/symptom/list")
    b = parse(raw)
    n = len(b["data"]) if ok_code(b) else -1
    return s == 200 and ok_code(b) and n == 9, f"http={s} 症状条数={n}"


case("TC-D01", "症状诊断", "GET /symptom/list 返回 9 条症状字典", t_symptom)


def t_checklist():
    s, raw = post_json("/diagnose/checklist",
                       {"symptomCodes": ["yellowing_whole", "wilting"], "archiveId": DEMO_ARCHIVE_ID})
    b = parse(raw)
    d = b.get("data") or {}
    if d.get("diagnosisId"):
        CTX["report_id"] = d["diagnosisId"]
    return (s == 200 and ok_code(b) and d.get("likely") and d.get("confidencePct") is not None,
            f"http={s} 报告id={d.get('diagnosisId')} 疑似={d.get('likely')} 置信={d.get('confidencePct')}%")


case("TC-D02", "症状诊断", "POST /diagnose/checklist 勾选 2 个症状生成报告", t_checklist)


def t_checklist_empty():
    s, raw = post_json("/diagnose/checklist", {"symptomCodes": []})
    b = parse(raw)
    return s == 200 and ok_code(b, 4001), f"http={s} code={b.get('code') if b else None} msg={b.get('msg') if b else None}"


case("TC-D03", "症状诊断", "POST /diagnose/checklist 空症状列表 → 4001", t_checklist_empty)


def t_checklist_missing():
    s, raw = post_json("/diagnose/checklist", {})
    b = parse(raw)
    return s == 200 and ok_code(b, 4001), f"http={s} code={b.get('code') if b else None}"


case("TC-D04", "症状诊断", "POST /diagnose/checklist 缺 symptomCodes → 4001", t_checklist_missing)


def t_checklist_bad():
    s, raw = post_json("/diagnose/checklist", {"symptomCodes": ["__no_such_code__"]})
    b = parse(raw)
    return s == 200 and ok_code(b, 4001), f"http={s} code={b.get('code') if b else None} msg={b.get('msg') if b else None}"


case("TC-D05", "症状诊断", "POST /diagnose/checklist 无效症状码 → 4001", t_checklist_bad)


def t_diag_photo():
    s, raw = post_file("/diagnose/photo", "image", "leaf.jpg", SAMPLE_IMG.read_bytes())
    b = parse(raw)
    d = b.get("data") or {}
    p = (d.get("imagePath") or "").replace("\\", "/")
    return s == 200 and ok_code(b) and "/diagnosis/" in p, f"http={s} 落盘={p}"


case("TC-D06", "症状诊断", "POST /diagnose/photo 病叶照片存档", t_diag_photo)


def t_diag_submit_gone():
    s, raw = get("/diagnose/submit?plantId=1")
    b = parse(raw)
    return not ok_code(b), f"http={s} code={b.get('code') if b else None}（会伪造诊断报告的死接口已移除）"


case("TC-D07", "症状诊断", "GET /diagnose/submit 已移除（回归守卫）", t_diag_submit_gone)


def t_feedback():
    rid = CTX.get("report_id", 1)
    s, raw = post_json("/diagnosis/feedback", {"reportId": rid, "ok": True})
    b = parse(raw)
    return s == 200 and ok_code(b), f"http={s} code={b.get('code') if b else None} reportId={rid}"


case("TC-D08", "症状诊断", "POST /diagnosis/feedback 提交纠错反馈", t_feedback)


def t_feedback_noid():
    s, raw = post_json("/diagnosis/feedback", {})
    b = parse(raw)
    return s == 200 and ok_code(b, 4001), f"http={s} code={b.get('code') if b else None}"


case("TC-D09", "症状诊断", "POST /diagnosis/feedback 缺 reportId → 4001", t_feedback_noid)


def t_feedback_404():
    s, raw = post_json("/diagnosis/feedback", {"reportId": 999999, "ok": True})
    b = parse(raw)
    return s == 200 and ok_code(b, 4040), f"http={s} code={b.get('code') if b else None}"


case("TC-D10", "症状诊断", "POST /diagnosis/feedback 报告不存在 → 4040", t_feedback_404)


# ================= 知识库 =================

def t_klist():
    s, raw = get("/knowledge/list")
    b = parse(raw)
    n = len(b["data"]) if ok_code(b) else -1
    return s == 200 and ok_code(b) and n == 20, f"http={s} 品种数={n}（必须 20，闭集分类对齐）"


case("TC-K01", "知识库", "GET /knowledge/list 返回 20 个品种", t_klist)


def t_ksearch():
    s, raw = get("/knowledge/list?keyword=%E7%BB%BF")   # 「绿」的 URL 编码
    b = parse(raw)
    data = b.get("data") or []
    hit = all("绿" in (x.get("name") or "") for x in data) if data else False
    return s == 200 and ok_code(b) and hit and len(data) >= 1, f"http={s} 命中 {len(data)} 条，均含关键字"


case("TC-K02", "知识库", "GET /knowledge/list?keyword=绿 关键字过滤", t_ksearch)


def t_kdetail():
    s, raw = get("/knowledge/detail?id=1")
    b = parse(raw)
    d = b.get("data") or {}
    # 注意：该接口返回的是养护详情，不含品种名（前端靠列表页已拿到的名称渲染标题）
    return (s == 200 and ok_code(b) and d.get("water") and d.get("habit") and d.get("faq") is not None,
            f"http={s} 字段={sorted(d.keys())}（无品种名字段，属现有契约）")


case("TC-K03", "知识库", "GET /knowledge/detail?id=1 返回养护详情", t_kdetail)


def t_kdetail_404():
    s, raw = get("/knowledge/detail?id=999999")
    b = parse(raw)
    return s == 200 and ok_code(b, 4040), f"http={s} code={b.get('code') if b else None}"


case("TC-K04", "知识库", "GET /knowledge/detail?id=999999 品种不存在 → 4040", t_kdetail_404)


def t_kdetail_bad():
    s, raw = get("/knowledge/detail?id=abc")
    b = parse(raw)
    msg = (b.get("msg") or "")[:70] if b else ""
    return s == 200 and ok_code(b, 4001), f"http={s} code={b.get('code') if b else None} msg={msg}（id 非数字，应报 4001）"


case("TC-K05", "知识库", "GET /knowledge/detail?id=abc 类型非法 → 应为 4001", t_kdetail_bad)


# ================= 家庭协作 =================

def t_family():
    s, raw = get("/family/info")
    b = parse(raw)
    d = b.get("data") or {}
    mem = d.get("members") or []
    return s == 200 and ok_code(b) and len(mem) >= 1, f"http={s} 成员数={len(mem)} 任务数={len(d.get('tasks') or [])}"


case("TC-F01", "家庭协作", "GET /family/info 返回成员与任务", t_family)


def t_task():
    s, raw = post_json("/family/task", {"archiveId": DEMO_ARCHIVE_ID, "title": "自动化测试任务", "taskType": "浇水"})
    b = parse(raw)
    d = b.get("data") or {}
    if d.get("id"):
        CTX["task_id"] = d["id"]
    return s == 200 and ok_code(b) and d.get("id"), f"http={s} 任务id={d.get('id')} 标题={d.get('title')} 完成={d.get('done')}"


case("TC-F02", "家庭协作", "POST /family/task 分配养护任务", t_task)


def t_task_done():
    tid = CTX.get("task_id", 1)
    s, raw = post_json("/family/task/done", {"id": tid, "done": True})
    b = parse(raw)
    d = b.get("data") or {}
    return s == 200 and ok_code(b) and d.get("done") is True, f"http={s} 任务id={tid} done={d.get('done')}"


case("TC-F03", "家庭协作", "POST /family/task/done 标记任务完成", t_task_done)


def t_task_done_noid():
    s, raw = post_json("/family/task/done", {})
    b = parse(raw)
    return s == 200 and ok_code(b, 4001), f"http={s} code={b.get('code') if b else None}"


case("TC-F04", "家庭协作", "POST /family/task/done 缺 id → 4001", t_task_done_noid)


def t_task_done_404():
    s, raw = post_json("/family/task/done", {"id": 999999, "done": True})
    b = parse(raw)
    return s == 200 and ok_code(b, 4040), f"http={s} code={b.get('code') if b else None}"


case("TC-F05", "家庭协作", "POST /family/task/done 任务不存在 → 4040", t_task_done_404)


# ================= 通知（写操作放最后） =================

def t_notice():
    s, raw = get("/notification/list")
    b = parse(raw)
    n = len(b["data"]) if ok_code(b) else -1
    return s == 200 and ok_code(b) and n >= 1, f"http={s} 通知数={n}"


case("TC-N01", "通知", "GET /notification/list 返回通知列表", t_notice)


def t_notice_unread():
    s, raw = get("/notification/list?isRead=0")
    b = parse(raw)
    data = b.get("data") or []
    # 注意：请求参数叫 isRead，但响应字段叫 read —— 命名不对称，易踩坑
    allunread = all(x.get("read") is False for x in data)
    return s == 200 and ok_code(b) and allunread, f"http={s} 未读数={len(data)}（响应字段为 read，请求参数为 isRead）"


case("TC-N02", "通知", "GET /notification/list?isRead=0 仅未读", t_notice_unread)


def t_read_noid():
    s, raw = post_json("/notification/read", {})
    b = parse(raw)
    return s == 200 and ok_code(b, 4001), f"http={s} code={b.get('code') if b else None}"


case("TC-N03", "通知", "POST /notification/read 缺 id → 4001", t_read_noid)


def t_read_404():
    s, raw = post_json("/notification/read", {"id": 999999})
    b = parse(raw)
    return s == 200 and ok_code(b, 4040), f"http={s} code={b.get('code') if b else None}"


case("TC-N04", "通知", "POST /notification/read 通知不存在 → 4040", t_read_404)


def t_read_one():
    s, raw = get("/notification/list?isRead=0")
    data = (parse(raw) or {}).get("data") or []
    if not data:
        return True, "无未读通知，跳过"
    nid = data[0].get("id")
    s2, raw2 = post_json("/notification/read", {"id": nid})
    b2 = parse(raw2)
    return s2 == 200 and ok_code(b2), f"标记通知 id={nid} 已读 code={b2.get('code') if b2 else None}"


case("TC-N05", "通知", "POST /notification/read 单条标记已读", t_read_one)


def t_read_all():
    s, raw = post_json("/notification/read-all", {})
    b = parse(raw)
    s2, raw2 = get("/notification/list?isRead=0")
    left = len((parse(raw2) or {}).get("data") or [])
    return s == 200 and ok_code(b) and left == 0, f"http={s} 剩余未读={left}"


case("TC-N06", "通知", "POST /notification/read-all 全部已读", t_read_all)


# ================= 档案编辑 / 删除 / 统计 / 导出 / 周建议 =================

def t_update():
    aid = CTX.get("new_archive_id")
    if not aid:
        return False, "前置建档用例未拿到 id，无法测试"
    s, raw = post_json("/plant/update", {
        "id": aid, "name": "编辑后名称", "location": "北阳台",
        "heightCm": 42, "waterIntervalDays": 6,
    })
    b = parse(raw)
    d = b.get("data") or {}
    env = d.get("env") or {}
    good = (s == 200 and ok_code(b) and d.get("name") == "编辑后名称"
            and d.get("familyName") == "北阳台" and d.get("heightCm") == 42)
    return good, (f"http={s} 名称={d.get('name')} 位置={d.get('familyName')} "
                  f"高度={d.get('heightCm')} 间隔={env.get('waterInterval')}")


case("TC-P13", "植物档案", "POST /plant/update 编辑名称/位置/高度/间隔", t_update)


def t_update_noid():
    s, raw = post_json("/plant/update", {"name": "x"})
    b = parse(raw)
    return s == 200 and ok_code(b, 4001), f"http={s} code={b.get('code') if b else None}"


case("TC-P14", "植物档案", "POST /plant/update 缺 id → 4001", t_update_noid)


def t_update_404():
    s, raw = post_json("/plant/update", {"id": 999999, "name": "x"})
    b = parse(raw)
    return s == 200 and ok_code(b, 4040), f"http={s} code={b.get('code') if b else None}"


case("TC-P15", "植物档案", "POST /plant/update 档案不存在 → 4040", t_update_404)


def t_delete_soft():
    """软删：列表与详情都应查不到；数据库里记录仍在（非物理删除，养护记录可追溯）。"""
    aid = CTX.get("new_archive_id")
    if not aid:
        return False, "前置建档用例未拿到 id，无法测试"
    s1, raw1 = post_json("/plant/delete", {"id": aid})
    b1 = parse(raw1)
    s2, raw2 = get(f"/plant/detail?id={aid}")
    b2 = parse(raw2)
    s3, raw3 = get("/plant/list")
    ids = [p["id"] for p in ((parse(raw3) or {}).get("data") or [])]
    good = s1 == 200 and ok_code(b1) and ok_code(b2, 4040) and aid not in ids
    return good, (f"删除 code={b1.get('code') if b1 else None}；"
                  f"删除后详情 code={b2.get('code') if b2 else None}；"
                  f"列表中仍存在={aid in ids}")


case("TC-P16", "植物档案", "POST /plant/delete 软删 → 列表/详情均不可见", t_delete_soft)


def t_delete_again():
    aid = CTX.get("new_archive_id", 999999)
    s, raw = post_json("/plant/delete", {"id": aid})
    b = parse(raw)
    return s == 200 and ok_code(b, 4040), \
        f"http={s} code={b.get('code') if b else None}（重复删除报不存在，而非 5000）"


case("TC-P17", "植物档案", "POST /plant/delete 重复删除 → 4040", t_delete_again)


def t_delete_noid():
    s, raw = post_json("/plant/delete", {})
    b = parse(raw)
    return s == 200 and ok_code(b, 4001), f"http={s} code={b.get('code') if b else None}"


case("TC-P18", "植物档案", "POST /plant/delete 缺 id → 4001", t_delete_noid)


def t_stats():
    s, raw = get(f"/plant/stats?id={DEMO_ARCHIVE_ID}")
    b = parse(raw)
    d = b.get("data") or {}
    bars = d.get("weekBars") or []
    good = (s == 200 and ok_code(b) and len(bars) == 4
            and all("count" in x and "pct" in x for x in bars)
            and isinstance(d.get("avgIntervalDays"), (int, float)))
    return good, (f"http={s} 周数据={[(x['label'], x['count']) for x in bars]} "
                  f"类型数={len(d.get('byType') or [])} 平均间隔={d.get('avgIntervalDays')}天 "
                  f"记录={d.get('recordCount')} 株高={d.get('heightCm')}")


case("TC-P19", "植物档案", "GET /plant/stats 真实聚合统计", t_stats)


def t_stats_404():
    s, raw = get("/plant/stats?id=999999")
    b = parse(raw)
    return s == 200 and ok_code(b, 4040), f"http={s} code={b.get('code') if b else None}"


case("TC-P20", "植物档案", "GET /plant/stats 档案不存在 → 4040", t_stats_404)


def t_export_xlsx():
    s, raw = _send("GET", BASE + "/plant/export")
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = z.namelist()
        need = ["[Content_Types].xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml"]
        all_in = all(n in names for n in need)
        intact = z.testzip() is None
        return s == 200 and all_in and intact, \
            f"http={s} 大小={len(raw)}B 合法zip={intact} 含必需部件={all_in}"
    except Exception as e:
        return False, f"http={s} 不是合法 xlsx: {e}"


case("TC-P21", "植物档案", "GET /plant/export 默认导出 xlsx（结构合法）", t_export_xlsx)


def t_export_csv():
    s, raw = _send("GET", BASE + "/plant/export?fmt=csv&recordsOnly=true")
    bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig", errors="replace")
    return s == 200 and bom and "档案ID" in text and "植物档案" not in text, \
        f"http={s} UTF-8 BOM={bom} 含记录表头={'档案ID' in text} 行数={text.count(chr(10))}（recordsOnly 应不含档案段）"


case("TC-P22", "植物档案", "GET /plant/export?fmt=csv 带 BOM 且仅记录", t_export_csv)


def t_weekly_plan():
    s, raw = get("/plan/weekly")
    b = parse(raw)
    d = b.get("data") or {}
    items = d.get("items") or []
    good = (s == 200 and ok_code(b) and d.get("message")
            and isinstance(d.get("totalCount"), int)
            and all("nextDue" in x and "advice" in x for x in items))
    return good, (f"http={s} 文案=「{d.get('message')}」 "
                  f"盆栽={d.get('totalCount')} 待浇={d.get('dueCount')}")


case("TC-L01", "养护计划", "GET /plan/weekly 按真实状态给建议", t_weekly_plan)


# ================= 鉴权与通用边界 =================

def t_no_auth():
    s, raw = get("/plant/list")
    b = parse(raw)
    return s == 200 and ok_code(b), f"http={s} code={b.get('code') if b else None}（无 token 回落演示用户，属设计行为）"


case("TC-A01", "鉴权", "无 Authorization 头访问 → 回落演示用户", t_no_auth)


def t_bad_token():
    s, raw = get("/plant/list", headers={"Authorization": "Bearer not-a-real-jwt"})
    b = parse(raw)
    return s == 200 and ok_code(b), f"http={s} code={b.get('code') if b else None}（无效 token 同样不返回 4010）"


case("TC-A02", "鉴权", "无效 JWT → 回落演示用户而非 4010", t_bad_token)


def t_404():
    s, raw = get("/no-such-endpoint")
    b = parse(raw)
    return s == 404, f"http={s} code={b.get('code') if b else None}（应为 404，实际落到统一 5000 兜底）"


case("TC-A03", "通用", "访问不存在路径 → 应返回 404", t_404)


def t_oversize():
    big = b"\xff\xd8\xff" + b"0" * (11 * 1024 * 1024)   # 11MB > max-file-size 10MB
    s, raw = post_file("/species/recognize", "image", "big.jpg", big)
    b = parse(raw)
    msg = (b.get("msg") or "")[:45] if b else ""
    return s == 413 or ok_code(b, 4001), f"http={s} code={b.get('code') if b else None} msg={msg}（已拒绝，但应归为超限而非服务器错误）"


case("TC-A04", "通用", "上传 11MB 文件超过 10MB 上限", t_oversize)


# ================= 执行 =================

def main():
    print("=" * 78)
    print("接口功能测试 —— 绿植智能养护系统")
    print("=" * 78)
    print(f"后端: {BASE}    AI: {AI}")
    print(f"样例图: {SAMPLE_IMG}（存在={SAMPLE_IMG.exists()}）")
    print()

    if not SAMPLE_IMG.exists():
        raise SystemExit(f"缺少样例图片: {SAMPLE_IMG}")

    for name, url in (("后端 8000", BASE + "/plant/list"), ("AI 5000", AI + "/health")):
        try:
            st, _ = _send("GET", url, timeout=5)
            print(f"[预检] {name} 可达 (http {st})")
        except Exception as e:
            raise SystemExit(f"[预检失败] {name} 不可达: {e}\n请先按《运行说明.md》第三节启动三个服务。")
    print()

    results, passed = [], 0
    t0 = time.time()

    for c in CASES:
        try:
            good, detail = c["fn"]()
        except Exception as e:
            good, detail = False, f"执行异常: {type(e).__name__}: {e}"
        passed += 1 if good else 0
        results.append({"cid": c["cid"], "module": c["module"], "title": c["title"],
                        "passed": bool(good), "detail": detail})
        print(f"[{'PASS' if good else 'FAIL'}] {c['cid']} {c['title']}")
        print(f"        {detail}")

    elapsed = time.time() - t0
    total = len(CASES)
    print()
    print("=" * 78)
    print(f"结果: {passed}/{total} 通过，{total - passed} 失败，耗时 {elapsed:.1f}s")
    print("=" * 78)

    by_module = {}
    for r in results:
        m = by_module.setdefault(r["module"], [0, 0])
        m[0] += 1 if r["passed"] else 0
        m[1] += 1
    for m, (p, n) in by_module.items():
        print(f"  {m}: {p}/{n}")

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULT_DIR / "api_result.json", "w", encoding="utf-8") as f:
        json.dump({"base": BASE, "ai": AI, "total": total, "passed": passed,
                   "failed": total - passed, "elapsed_seconds": round(elapsed, 2),
                   "cases": results}, f, ensure_ascii=False, indent=2)

    with open(RESULT_DIR / "api_result.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["用例编号", "模块", "用例标题", "结论", "实际结果"])
        for r in results:
            w.writerow([r["cid"], r["module"], r["title"], "通过" if r["passed"] else "失败", r["detail"]])

    print(f"\n结果已保存: {RESULT_DIR / 'api_result.json'} / api_result.csv")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
