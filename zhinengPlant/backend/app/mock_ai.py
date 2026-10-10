"""
mock_ai.py —— 识别/诊断的占位推理
这里先返回与接口文档一致的 mock 结果，保证前后端联调跑通。
真实模型接入：把 recognize() / diagnose() 里的 mock 换成加载训练好的模型推理
（训练见 Colab Notebook；模型文件放 backend/models/ 下）。
"""
import json


def recognize():
    """品种识别（mock）：真实实现 = 加载品种分类模型，预处理图片，返回 top-k"""
    return {
        "candidates": [
            {"speciesId": 1001, "species": "绿萝", "confidence": 0.94, "desc": "天南星科，喜温暖湿润，耐半阴"},
            {"speciesId": 1002, "species": "龟背竹", "confidence": 0.41, "desc": "相似品种，叶片裂叶形态略小"},
            {"speciesId": 1003, "species": "虎皮兰", "confidence": 0.18, "desc": "差异较大，仅供参考"},
        ]
    }


def diagnose():
    """健康诊断（mock）：真实实现 = 加载病害多标签模型，返回症状概率 + 报告"""
    return {
        "diagnosisId": 21,
        "symptoms": [
            {"code": "yellowing_edge", "label": "叶缘黄化", "prob": 0.91, "active": True},
            {"code": "overwater", "label": "水多", "prob": 0.78, "active": True},
        ],
        "report": {
            "suspectProblem": "疑似浇水过多导致的叶缘黄化",
            "causeAnalysis": "土壤长期潮湿、排水不畅，根系缺氧导致叶缘黄化。",
            "emergencySteps": "1.立即停水并松土通风 2.检查盆底积水 3.剪除严重黄叶",
            "longTermAdvice": "调整至见干见湿，雨季降低浇水频次。",
        },
    }
