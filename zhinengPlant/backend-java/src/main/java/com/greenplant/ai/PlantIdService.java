package com.greenplant.ai;

import com.greenplant.common.BizException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.multipart.MultipartFile;

import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 使用 Plant.id API v3 完成真实植物品种识别和健康诊断。 */
@Service
public class PlantIdService {

    private final RestClient client;

    @Value("${plant-id.base-url:https://api.plant.id/v3}")
    private String baseUrl;

    @Value("${plant-id.api-key:}")
    private String apiKey;

    public PlantIdService() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(10_000);
        factory.setReadTimeout(30_000);
        this.client = RestClient.builder().requestFactory(factory).build();
    }

    public Map<String, Object> recognize(MultipartFile image) {
        validate(image);

        try {
            Map<String, Object> response = postImage(
                    "/identification?details=common_names&language=zh", image);
            return adaptResponse(response);
        } catch (BizException e) {
            throw e;
        } catch (RestClientResponseException e) {
            int status = e.getStatusCode().value();
            if (status == 401 || status == 403) {
                throw new BizException(5000, "Plant.id API 密钥无效或无权限");
            }
            if (status == 429) {
                throw new BizException(5000, "Plant.id API 调用额度已用完，请稍后再试");
            }
            throw new BizException(5000, "Plant.id 识别服务请求失败（" + status + "）");
        } catch (Exception e) {
            throw new BizException(5000, "Plant.id 识别服务暂时不可用");
        }
    }

    /**
     * 调用 Plant.id 的 plant.health 模型。返回值同时保留结构化字段和小程序页面直接使用的扁平字段。
     */
    public Map<String, Object> diagnose(MultipartFile image) {
        validate(image);
        try {
            Map<String, Object> response = postImage(
                    "/health_assessment?details=local_name,description,treatment,cause,common_names&language=zh",
                    image);
            return adaptHealthResponse(response);
        } catch (BizException e) {
            throw e;
        } catch (RestClientResponseException e) {
            throw apiException(e);
        } catch (Exception e) {
            throw new BizException(5000, "Plant.id 健康诊断服务暂时不可用");
        }
    }

    private void validate(MultipartFile image) {
        if (apiKey == null || apiKey.isBlank()) {
            throw new BizException(5000, "Plant.id API 密钥未配置");
        }
        if (image == null || image.isEmpty()) {
            throw new BizException(4001, "缺少图片");
        }
        if (image.getSize() > 10 * 1024 * 1024L) {
            throw new BizException(4001, "图片不能超过10MB");
        }
        String contentType = image.getContentType();
        if (contentType != null && !contentType.startsWith("image/")) {
            throw new BizException(4001, "仅支持图片文件");
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> postImage(String path, MultipartFile image) throws Exception {
        String encoded = Base64.getEncoder().encodeToString(image.getBytes());
        return client.post()
                .uri(baseUrl + path)
                .contentType(MediaType.APPLICATION_JSON)
                .header("Api-Key", apiKey)
                .body(Map.of("images", List.of(encoded)))
                .retrieve()
                .body(Map.class);
    }

    private BizException apiException(RestClientResponseException e) {
        int status = e.getStatusCode().value();
        if (status == 401 || status == 403) {
            return new BizException(5000, "Plant.id API 密钥无效或无权限");
        }
        if (status == 429) {
            return new BizException(5000, "Plant.id API 调用额度已用完，请稍后再试");
        }
        return new BizException(5000, "Plant.id 服务请求失败（" + status + "）");
    }

    private Map<String, Object> adaptResponse(Map<String, Object> response) {
        Map<String, Object> result = asMap(response == null ? null : response.get("result"));
        Map<String, Object> isPlant = asMap(result.get("is_plant"));
        if (Boolean.FALSE.equals(isPlant.get("binary"))) {
            throw new BizException(6001, "照片中未识别到植物，请重新拍摄");
        }

        Map<String, Object> classification = asMap(result.get("classification"));
        List<Map<String, Object>> suggestions = asMapList(classification.get("suggestions"));
        if (suggestions.isEmpty()) {
            throw new BizException(6001, "无法确认植物品种，请换一张清晰照片");
        }

        List<Map<String, Object>> candidates = new ArrayList<>();
        for (int i = 0; i < Math.min(3, suggestions.size()); i++) {
            Map<String, Object> suggestion = suggestions.get(i);
            String scientificName = stringValue(suggestion.get("name"), "未知植物");
            Map<String, Object> details = asMap(suggestion.get("details"));
            List<?> commonNames = details.get("common_names") instanceof List<?> list ? list : List.of();
            String displayName = commonNames.isEmpty()
                    ? scientificName
                    : stringValue(commonNames.get(0), scientificName);
            double probability = suggestion.get("probability") instanceof Number number
                    ? number.doubleValue() : 0D;

            Map<String, Object> candidate = new LinkedHashMap<>();
            candidate.put("speciesId", suggestion.get("id"));
            candidate.put("species", displayName);
            candidate.put("confidence", probability);
            candidate.put("desc", scientificName);
            candidates.add(candidate);
        }

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("candidates", candidates);
        data.put("provider", "Plant.id");
        return data;
    }

    private Map<String, Object> adaptHealthResponse(Map<String, Object> response) {
        Map<String, Object> result = asMap(response == null ? null : response.get("result"));
        Map<String, Object> isPlant = asMap(result.get("is_plant"));
        if (Boolean.FALSE.equals(isPlant.get("binary"))) {
            throw new BizException(6001, "照片中未识别到植物，请重新拍摄");
        }

        Map<String, Object> isHealthy = asMap(result.get("is_healthy"));
        boolean healthy = Boolean.TRUE.equals(isHealthy.get("binary"));
        double healthyProbability = numberValue(isHealthy.get("probability"));
        List<Map<String, Object>> suggestions = asMapList(asMap(result.get("disease")).get("suggestions"));

        List<Map<String, Object>> symptoms = new ArrayList<>();
        for (int i = 0; i < Math.min(3, suggestions.size()); i++) {
            Map<String, Object> suggestion = suggestions.get(i);
            Map<String, Object> details = asMap(suggestion.get("details"));
            String rawName = stringValue(suggestion.get("name"), "未知健康问题");
            String label = diseaseName(details, rawName);
            Map<String, Object> symptom = new LinkedHashMap<>();
            symptom.put("code", stringValue(suggestion.get("id"), rawName));
            symptom.put("label", label);
            symptom.put("prob", numberValue(suggestion.get("probability")));
            symptom.put("active", true);
            symptoms.add(symptom);
        }

        Map<String, Object> top = suggestions.isEmpty() ? Map.of() : suggestions.get(0);
        Map<String, Object> details = asMap(top.get("details"));
        String rawName = stringValue(top.get("name"), "未发现明显病害");
        String diseaseName = diseaseName(details, rawName);
        double confidence = healthy ? healthyProbability : numberValue(top.get("probability"));
        String description = stringValue(details.get("description"), "");
        String cause = stringValue(details.get("cause"), "");
        Map<String, Object> treatment = asMap(details.get("treatment"));
        String urgent = joinTreatment(treatment.get("biological"), treatment.get("chemical"));
        String prevention = joinTreatment(treatment.get("prevention"));

        String likely;
        String causeAnalysis;
        if (healthy) {
            likely = "植物整体健康，未发现明显病害";
            causeAnalysis = "Plant.id 健康模型未检测到需要优先处理的病虫害或生理问题。";
            urgent = "暂不需要紧急处理，继续观察叶片、茎部和土壤状态。";
            prevention = "保持适宜的光照、通风和浇水频率，定期检查叶片正反面。";
        } else {
            likely = "疑似" + diseaseName;
            causeAnalysis = !description.isBlank() ? description
                    : (!cause.isBlank() ? "可能由“" + cause + "”引起。" : "请结合叶片、土壤和近期养护情况进一步判断。");
            if (urgent.isBlank()) {
                urgent = "隔离受影响植株，剪除严重受损部位，并暂停不必要的浇水或施肥。";
            }
            if (prevention.isBlank()) {
                prevention = "改善通风与光照，按需浇水，并持续观察新叶和病斑变化。";
            }
        }

        Map<String, Object> report = new LinkedHashMap<>();
        report.put("suspectProblem", likely);
        report.put("causeAnalysis", causeAnalysis);
        report.put("emergencySteps", urgent);
        report.put("longTermAdvice", prevention);

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("healthy", healthy);
        data.put("confidence", confidence);
        data.put("likely", likely);
        data.put("cause", causeAnalysis);
        data.put("urgent", urgent);
        data.put("longTerm", prevention);
        data.put("symptoms", symptoms);
        data.put("report", report);
        data.put("provider", "Plant.id plant.health");
        return data;
    }

    private String diseaseName(Map<String, Object> details, String rawName) {
        String localName = stringValue(details.get("local_name"), "");
        if (!localName.isBlank()) {
            return localName;
        }
        Object common = details.get("common_names");
        if (common instanceof List<?> names && !names.isEmpty()) {
            return stringValue(names.get(0), translateDisease(rawName));
        }
        return translateDisease(rawName);
    }

    private String translateDisease(String name) {
        return switch (name.toLowerCase()) {
            case "water excess or uneven watering" -> "浇水过多或不均匀";
            case "water deficiency" -> "缺水";
            case "water-related issue" -> "水分管理问题";
            case "nutrient deficiency" -> "营养不足";
            case "mechanical damage" -> "机械损伤";
            case "light excess" -> "光照过强";
            case "lack of light" -> "光照不足";
            case "dry air" -> "空气干燥";
            case "senescence" -> "自然衰老";
            case "feeding damage by insects" -> "虫害取食损伤";
            case "fungi" -> "真菌性病害";
            case "bacteria" -> "细菌性病害";
            case "viruses" -> "病毒性病害";
            case "abiotic" -> "非生物性胁迫";
            default -> name;
        };
    }

    private String joinTreatment(Object... values) {
        List<String> parts = new ArrayList<>();
        for (Object value : values) {
            if (value instanceof List<?> list) {
                for (Object item : list) {
                    String text = stringValue(item, "").trim();
                    if (!text.isBlank()) parts.add(text);
                }
            } else {
                String text = stringValue(value, "").trim();
                if (!text.isBlank()) parts.add(text);
            }
        }
        return String.join("；", parts);
    }

    private double numberValue(Object value) {
        return value instanceof Number number ? number.doubleValue() : 0D;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> asMap(Object value) {
        return value instanceof Map<?, ?> ? (Map<String, Object>) value : Map.of();
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> asMapList(Object value) {
        return value instanceof List<?> ? (List<Map<String, Object>>) value : List.of();
    }

    private String stringValue(Object value, String fallback) {
        return value == null || String.valueOf(value).isBlank() ? fallback : String.valueOf(value);
    }
}
