package com.greenplant.dto;

import java.math.BigDecimal;

public record PlantUpdateReq(
        String name,
        String potMaterial,
        BigDecimal initHeightCm,
        String emotionTag,
        String status
) {
}
