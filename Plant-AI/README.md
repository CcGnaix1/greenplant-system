# 绿植智能养护系统 —— AI 模块（独立包）

本包是从「绿植智能养护系统」中**分离出来的 AI 部分**，包含品种识别与症状识别的
**训练脚本、推理服务、已上线模型**与相关文档。前端（微信小程序）与后端（Spring Boot）
不在本包内。

> 导出时间：2026-10-03 ｜ Python 3.11 ｜ 模型版本：品种 42 类 / 症状 6 类

## 目录结构

```
Plant-AI/
├─ ml/                    训练脚本（数据采集、训练、评估、导出 ONNX）
│  ├─ train30.py          品种模型训练（42 类入口）
│  ├─ train_symptom2.py   症状模型训练（含背景合成）
│  ├─ export_onnx.py      导出 ONNX
│  ├─ dataset.py / config.py
│  ├─ species.json        42 类品种配置（单一事实来源）
│  ├─ symptom_taxonomy.json  6 症状类定义 + 38 类映射
│  └─ requirements.txt    训练依赖
├─ service/               推理服务（FastAPI）
│  ├─ main.py             HTTP 接口（/recognize /diagnose /analyze /health ...）
│  ├─ recognizer.py       品种推理（ONNX + 320 预处理 + TTA）
│  ├─ symptom.py          症状推理（ONNX + 224 预处理）
│  └─ requirements.txt    推理依赖
├─ output/                品种模型（服务实际加载）
│  ├─ plant_model.onnx    42 类 ONNX
│  ├─ labels.json         42 类标签 + knowledge_id 映射
│  ├─ best_model.pth      PyTorch 权重（重训/导出用）
│  ├─ history.json        训练曲线
│  └─ result.json         指标汇总
├─ output_symptom/        症状模型（服务实际加载）
│  ├─ plant_symptom.onnx  6 类 ONNX
│  ├─ labels.json  best_model.pth  history.json  result.json
├─ tests/                 评估与校验脚本（见「路径注意」）
├─ docs/                  运行说明 / 训练进度 / 病害识别进度 / 测试报告
├─ requirements.txt       完整锁定环境（pip freeze）
└─ README.md
```

## 模型信息

| | 品种识别 | 症状识别 |
|---|---|---|
| 类别数 | 42 | 6（healthy / leaf_spot / yellowing / powdery_mildew / pest_damage / rust）|
| 网络 | EfficientNet-B0 | MobileNetV3-Large |
| 输入分辨率 | 320×320 | 224×224 |
| TTA | 3 视角（1.0 / 0.88 / 1.12）| 无 |
| 识别率 | 室内测试 **0.9302**（Top-3 0.9690）／野外验证 0.9523 | 见 `docs/病害识别进度.md` |

> 品种模型的实际精度天花板是**数据标签噪声**（iNat 社区标注错标），见 `docs/测试报告.md` 第十节。

## 运行推理服务

服务用**相对路径**解析模型（`service/` 的上级目录即包根），因此**放到任何位置都能跑**，
只要保持 `output/` `output_symptom/` 与 `service/` 同级。

```bash
# 1) 装依赖（建议新建虚拟环境）
pip install -r service/requirements.txt

# 2) 启动（在 service/ 目录下）
cd service
python -m uvicorn main:app --host 0.0.0.0 --port 5000

# 3) 自检：应返回 isMock=false、品种 42 类、症状 6 类
curl http://127.0.0.1:5000/health
```

**上传目录**：`recognizer.py` 默认只允许 `C:/Plant/upload` 下的文件（防目录穿越）。
换机器时用环境变量覆盖：

```bash
export PLANT_UPLOAD_ROOT=/path/to/upload      # Git Bash
set PLANT_UPLOAD_ROOT=D:\path\to\upload       # cmd
```

其它可覆盖项：`PLANT_MODEL_IMAGE_SIZE`（默认 320）、`PLANT_TTA`（设 0 关 TTA）、
`PLANT_SYMPTOM_MODEL` / `PLANT_LABELS_PATH` 等。

## 重新训练

```bash
pip install -r ml/requirements.txt
# torch/torchvision 是 CUDA 版，需从 PyTorch 官方源装，见 requirements.txt 头部说明

cd ml
# 品种模型（42 类，EfficientNet-B0 @320，全量重训约 1 小时 / RTX 3060）
python train30.py --arch efficientnet_b0 --image-size 320 --batch-size 24 \
  --epochs 20 --init "" --out-dir ../output

# 导出 ONNX（--arch 必须与训练一致，否则 load_state_dict 报 size mismatch）
python export_onnx.py --model_path ../output/best_model.pth \
  --labels_path ../output/labels.json --output ../output/plant_model.onnx \
  --image-size 320 --arch efficientnet_b0
```

> 训练数据不在本包内（约 6.4 GB）。重训前需先采集/准备 `data/plants`（野外）与
> `data/plants_indoor`（室内），采集脚本见 `ml/fetch_*.py`。

## 路径注意（重要）

`tests/` 下的脚本大多**写死了** `ROOT = Path("C:/Plant/plant-ai")`，在本包位置**直接跑会报错**。
三种处理方式：

1. 把本包放到 `C:/Plant/plant-ai`（与原工程一致）——即可直接运行；
2. 或把脚本里的 `ROOT` 改成 `Path(__file__).resolve().parent.parent`；
3. 或只跑 `tests/accuracy_test.py`（它用的是相对路径）。

`service/` 不受影响（已用相对路径）。

## 主要接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 两个模型状态（`isMock` / 类别数 / 图像尺寸 / tta）|
| POST | `/recognize` | 品种识别（multipart，字段名 `image`）|
| POST | `/diagnose` | 症状识别 |
| POST | `/analyze` | 品种 + 症状一次返回 |
| POST | `/reload` | 热加载模型（换模型后无需重启）|

详见 `docs/运行说明.md`。
