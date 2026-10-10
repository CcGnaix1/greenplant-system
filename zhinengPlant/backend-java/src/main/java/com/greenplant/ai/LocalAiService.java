package com.greenplant.ai;

import com.greenplant.common.BizException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.multipart.MultipartFile;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** 调用组员训练的本地 FastAPI/ONNX 模型。 */
@Service
public class LocalAiService {

    private final RestClient client;

    @Value("${ai.local.base-url:http://127.0.0.1:5001}")
    private String baseUrl;

    @Value("${app.upload-dir:./uploads}")
    private String uploadDir;

    public LocalAiService() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(5_000);
        factory.setReadTimeout(45_000);
        this.client = RestClient.builder().requestFactory(factory).build();
    }

    public Map<String, Object> recognize(MultipartFile image) {
        return withImage(image, path -> adaptRecognition(post("/recognize", path)));
    }

    public Map<String, Object> diagnose(MultipartFile image) {
        return withImage(image, path -> adaptDiagnosis(post("/diagnose", path)));
    }

    private Map<String, Object> withImage(MultipartFile image, ImageCall call) {
        validate(image);
        Path temp = null;
        try {
            Path dir = Paths.get(uploadDir).toAbsolutePath().normalize().resolve("ai");
            Files.createDirectories(dir);
            temp = dir.resolve(UUID.randomUUID() + extension(image.getOriginalFilename()));
            image.transferTo(temp);
            return call.execute(temp);
        } catch (BizException e) {
            throw e;
        } catch (RestClientResponseException e) {
            throw new BizException(5000, "本地 AI 服务请求失败（" + e.getStatusCode().value() + "）");
        } catch (Exception e) {
            throw new BizException(5000, "本地 AI 服务不可用，请确认端口 5001 的推理服务已启动");
        } finally {
            if (temp != null) {
                try {
                    Files.deleteIfExists(temp);
                } catch (Exception ignored) {
                    // 临时文件清理失败不影响本次识别结果。
                }
            }
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> post(String endpoint, Path imagePath) {
        Map<String, Object> body = Map.of(
                "image_path", imagePath.toString(),
                "top_k", 3
        );
        return client.post()
                .uri(trimSlash(baseUrl) + endpoint)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(Map.class);
    }

    private Map<String, Object> adaptRecognition(Map<String, Object> response) {
        if (response == null || !Boolean.TRUE.equals(response.get("success"))) {
            throw new BizException(5000, "本地品种识别失败");
        }
        if (Boolean.TRUE.equals(response.get("is_mock"))) {
            throw new BizException(5000, "本地品种模型未正确加载，已拒绝返回模拟结果");
        }

        List<Map<String, Object>> source = asMapList(response.get("candidates"));
        List<Map<String, Object>> candidates = new ArrayList<>();
        // 页面只需要最终识别结果，不展示第二、第三候选。
        for (Map<String, Object> item : source.stream().limit(1).toList()) {
            Map<String, Object> candidate = new LinkedHashMap<>();
            candidate.put("speciesId", item.get("knowledgeId"));
            candidate.put("species", stringValue(item.get("species"), "未知植物"));
            candidate.put("confidence", numberValue(item.get("confidence")));
            candidates.add(candidate);
        }
        if (candidates.isEmpty()) {
            throw new BizException(6001, "未能识别植物，请换一张清晰照片");
        }

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("candidates", candidates);
        return data;
    }

    private Map<String, Object> adaptDiagnosis(Map<String, Object> response) {
        if (response == null || !Boolean.TRUE.equals(response.get("success"))) {
            throw new BizException(5000, "本地健康诊断失败");
        }
        if (Boolean.TRUE.equals(response.get("is_mock"))) {
            throw new BizException(5000, "本地症状模型未正确加载，已拒绝返回模拟结果");
        }
        boolean healthy = Boolean.TRUE.equals(response.get("healthy"));
        double confidence = numberValue(response.get("confidence"));
        // 与品种识别统一：只有严格超过 50% 才返回诊断结果。
        // 不采用 Python 模型原先 healthy=60% / disease=55% 的差异阈值。
        if (confidence <= 0.5) {
            throw new BizException(6001, "诊断未成功，请上传更清楚的图片");
        }
        String code = stringValue(response.get("symptom"), healthy ? "healthy" : "unknown");
        String label = stringValue(response.get("symptomLabel"), healthy ? "健康" : "未知症状");
        Advice advice = adviceFor(code, label, healthy);

        List<Map<String, Object>> symptoms = new ArrayList<>();
        // 健康诊断同样只保留最高置信度的最终症状，不返回其他候选。
        for (Map<String, Object> item : asMapList(response.get("candidates")).stream().limit(1).toList()) {
            Map<String, Object> symptom = new LinkedHashMap<>();
            symptom.put("code", stringValue(item.get("dictCode"), stringValue(item.get("symptom"), "unknown")));
            symptom.put("label", stringValue(item.get("label"), "未知症状"));
            symptom.put("prob", numberValue(item.get("confidence")));
            symptom.put("active", true);
            symptoms.add(symptom);
        }

        Map<String, Object> report = new LinkedHashMap<>();
        report.put("suspectProblem", advice.likely());
        report.put("causeAnalysis", advice.cause());
        report.put("emergencySteps", advice.urgent());
        report.put("longTermAdvice", advice.longTerm());

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("healthy", healthy);
        data.put("confidence", confidence);
        data.put("likely", advice.likely());
        data.put("cause", advice.cause());
        data.put("urgent", advice.urgent());
        data.put("longTerm", advice.longTerm());
        data.put("symptoms", symptoms);
        data.put("report", report);
        return data;
    }

    private Advice adviceFor(String code, String label, boolean healthy) {
        if (healthy) {
            return new Advice("植物整体健康，未发现明显症状",
                    "本地症状模型未检测到需要优先处理的异常。",
                    "暂不需要紧急处理，继续观察叶片和土壤状态。",
                    "保持适宜光照、通风和浇水频率，定期检查叶片正反面。");
        }
        return switch (code) {
            case "leaf_spot" -> new Advice("疑似" + label,
                    "叶斑可能与真菌、细菌感染或叶面长期潮湿有关。",
                    "隔离植株，剪除严重病叶，避免叶面继续积水。",
                    "改善通风，浇水时避开叶片，并持续观察病斑是否扩散。");
            case "pest_damage" -> new Advice("疑似" + label,
                    "叶片损伤可能由螨类或刺吸式害虫取食造成。",
                    "隔离植株，检查叶背并清理可见虫体和严重受害叶。",
                    "保持环境清洁和通风，定期检查新叶及叶片背面。");
            case "powdery_mildew" -> new Advice("疑似" + label,
                    "高湿、通风不足时叶面容易出现白色粉状病斑。",
                    "隔离植株并剪除重病叶，降低叶面湿度。",
                    "增加通风和株间距，避免夜间叶面长期潮湿。");
            case "rust" -> new Advice("疑似" + label,
                    "叶面锈色斑点可能与真菌性锈病有关。",
                    "隔离植株，移除严重病叶并清理落叶。",
                    "加强通风，避免叶面喷水，持续检查新生叶片。");
            case "yellowing" -> new Advice("疑似" + label,
                    "黄化可能与浇水不当、光照不足、缺肥或根系状态有关。",
                    "检查盆土干湿和根部状态，暂停盲目浇水或施肥。",
                    "根据植物习性调整光照和浇水，恢复后再少量施肥。");
            default -> new Advice("疑似" + label,
                    "模型检测到叶片异常，需要结合近期养护情况进一步判断。",
                    "隔离并观察植株，剪除严重受损部位。",
                    "改善通风和光照，按需浇水并记录症状变化。");
        };
    }

    private void validate(MultipartFile image) {
        if (image == null || image.isEmpty()) throw new BizException(4001, "缺少图片");
        if (image.getSize() > 10 * 1024 * 1024L) throw new BizException(4001, "图片不能超过10MB");
        String contentType = image.getContentType();
        if (contentType != null && !contentType.startsWith("image/")) {
            throw new BizException(4001, "仅支持图片文件");
        }
    }

    private String extension(String filename) {
        if (filename == null) return ".jpg";
        int dot = filename.lastIndexOf('.');
        String ext = dot >= 0 ? filename.substring(dot).toLowerCase() : ".jpg";
        return ext.matches("\\.(jpg|jpeg|png|webp)") ? ext : ".jpg";
    }

    private String trimSlash(String value) {
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> asMapList(Object value) {
        return value instanceof List<?> ? (List<Map<String, Object>>) value : List.of();
    }

    private String stringValue(Object value, String fallback) {
        return value == null || String.valueOf(value).isBlank() ? fallback : String.valueOf(value);
    }

    private double numberValue(Object value) {
        return value instanceof Number number ? number.doubleValue() : 0D;
    }

    private interface ImageCall {
        Map<String, Object> execute(Path path);
    }

    private record Advice(String likely, String cause, String urgent, String longTerm) {}
}
