package com.greenplant.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;

public record PlantCreateReq(
        @NotBlank(message = "植物名称不能为空") String name,
        @NotNull(message = "品种不能为空") Long speciesId,
        String potMaterial,
        BigDecimal initHeightCm,
        String emotionTag
) {
}
