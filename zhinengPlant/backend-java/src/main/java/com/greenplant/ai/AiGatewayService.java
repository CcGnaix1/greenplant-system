package com.greenplant.ai;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.util.Map;

/** 根据配置选择本地模型或 Plant.id；当前默认使用组员训练的本地模型。 */
@Service
public class AiGatewayService {

    private final LocalAiService localAiService;
    private final PlantIdService plantIdService;

    @Value("${ai.provider:local}")
    private String provider;

    public AiGatewayService(LocalAiService localAiService, PlantIdService plantIdService) {
        this.localAiService = localAiService;
        this.plantIdService = plantIdService;
    }

    public Map<String, Object> recognize(MultipartFile image) {
        return usePlantId() ? plantIdService.recognize(image) : localAiService.recognize(image);
    }

    public Map<String, Object> diagnose(MultipartFile image) {
        return usePlantId() ? plantIdService.diagnose(image) : localAiService.diagnose(image);
    }

    private boolean usePlantId() {
        return "plant-id".equalsIgnoreCase(provider);
    }
}
