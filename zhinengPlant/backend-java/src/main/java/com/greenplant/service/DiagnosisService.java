package com.greenplant.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import com.greenplant.ai.MockAiService;
import com.greenplant.ai.AiGatewayService;
import com.greenplant.common.BizException;
import com.greenplant.common.Result;
import com.greenplant.entity.DiagnosisRecord;
import com.greenplant.mapper.DiagnosisRecordMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.web.multipart.MultipartFile;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 识别与诊断：
 * - POST /api/species/recognize  品种识别（multipart 图片字段 image）
 * - POST /api/diagnosis          健康诊断（multipart 图片字段 image + 可选 plantId）
 */
@Service
@RequiredArgsConstructor
/** AI 业务：转发本地模型推理、执行置信度规则并保存诊断记录。 */
public class DiagnosisService {

    private static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final MockAiService aiService;
    private final AiGatewayService aiGatewayService;
    private final DiagnosisRecordMapper diagnosisMapper;

    /** 识别植物品种；最高置信度不超过 50% 时返回“请上传清楚图片”。 */
    public Result<Map<String, Object>> recognize(MultipartFile image) {
        if (image == null || image.isEmpty()) {
            throw new BizException(4001, "缺少图片");
        }
        Map<String, Object> data = aiGatewayService.recognize(image);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> candidates = (List<Map<String, Object>>) data.get("candidates");
        double top = candidates.isEmpty() ? 0 : (Double) candidates.get(0).get("confidence");
        // 最高候选必须严格超过 50% 才认为识别成功；50% 及以下要求重新拍摄。
        if (top <= 0.5) {
            return Result.error(6001, "未识别成功，请上传更清楚的图片");
        }
        return Result.ok(data);
    }

    /** 诊断植物健康状况，并把症状、报告和用户信息写入诊断历史。 */
    @Transactional
    public Result<Map<String, Object>> diagnosis(MultipartFile image,
                                                 Long plantId) {
        if (image == null || image.isEmpty()) {
            throw new BizException(4001, "缺少图片");
        }
        Map<String, Object> data = aiGatewayService.diagnose(image);

        DiagnosisRecord d = new DiagnosisRecord();
        d.setPlantId(plantId == null ? 0L : plantId);
        d.setUserId(com.greenplant.common.UserContext.get());
        d.setSymptoms(aiService.toJson(data.get("symptoms")));
        d.setReport(aiService.toJson(data.get("report")));
        d.setFeedback(0);
        d.setCreatedAt(LocalDateTime.now());
        diagnosisMapper.save(d);

        data.put("diagnosisId", d.getId());
        return Result.ok(data);
    }

    /** 查询一条诊断历史并恢复为前端需要的结构。 */
    public Result<Map<String, Object>> detail(Long diagId) {
        DiagnosisRecord d = diagnosisMapper.findById(diagId)
                .orElseThrow(() -> new BizException(4040, "诊断记录不存在"));
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("diagnosisId", d.getId());
        data.put("symptoms", aiService.toJson(d.getSymptoms()));
        data.put("report", aiService.toJson(d.getReport()));
        data.put("createdAt", d.getCreatedAt() == null ? null : d.getCreatedAt().format(FMT));
        return Result.ok(data);
    }

    /** 将用户反馈标记到指定诊断记录。 */
    @Transactional
    public Result<Map<String, Object>> feedback(Long diagId) {
        DiagnosisRecord d = diagnosisMapper.findById(diagId)
                .orElseThrow(() -> new BizException(4040, "诊断记录不存在"));
        d.setFeedback(1);
        diagnosisMapper.save(d);
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("diagnosisId", diagId);
        data.put("feedback", true);
        return Result.ok(data);
    }
}
