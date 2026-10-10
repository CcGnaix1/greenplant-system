package com.greenplant.ai;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 品种识别 / 健康诊断占位推理。
 * 换真实模型时：加载 models/ 下的训练权重（Colab 训练后导出），
 * 替换 recognize() / diagnose() 内部实现即可，接口契约不变。
 */
@Service
public class MockAiService {

    private final ObjectMapper mapper = new ObjectMapper();

    /** 品种识别：返回候选列表，结构对齐接口文档 */
    public Map<String, Object> recognize() {
        List<Map<String, Object>> candidates = List.of(
                cand(1001L, "绿萝", 0.94, "天南星科，喜温暖湿润，耐半阴"),
                cand(1002L, "龟背竹", 0.41, "相似品种，叶片裂叶形态略小"),
                cand(1003L, "虎皮兰", 0.18, "差异较大，仅供参考"));
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("candidates", candidates);
        return data;
    }

    private Map<String, Object> cand(Long id, String name, double conf, String desc) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("speciesId", id);
        m.put("species", name);
        m.put("confidence", conf);
        m.put("desc", desc);
        return m;
    }

    /** 健康诊断：症状多标签 + 诊断报告 */
    public Map<String, Object> diagnose() {
        List<Map<String, Object>> symptoms = List.of(
                sym("yellowing_edge", "叶缘黄化", 0.91),
                sym("overwater", "水多", 0.78));

        Map<String, Object> report = new LinkedHashMap<>();
        report.put("suspectProblem", "疑似浇水过多导致的叶缘黄化");
        report.put("causeAnalysis", "土壤长期潮湿、排水不畅，根系缺氧导致叶缘黄化。");
        report.put("emergencySteps", "1.立即停水并松土通风 2.检查盆底积水 3.剪除严重黄叶");
        report.put("longTermAdvice", "调整至见干见湿，雨季降低浇水频次。");

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("symptoms", symptoms);
        data.put("report", report);
        return data;
    }

    private Map<String, Object> sym(String code, String label, double prob) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("code", code);
        m.put("label", label);
        m.put("prob", prob);
        m.put("active", true);
        return m;
    }

    public String toJson(Object o) {
        try {
            return mapper.writeValueAsString(o);
        } catch (Exception e) {
            return "{}";
        }
    }
}
