package com.greenplant.entity;

import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
public class PlantProfile {

    private Long id;

    private Long userId;

    private Long speciesId;

    private String name;

    private String potMaterial;

    private BigDecimal initHeightCm;

    private String emotionTag;

    private String status;

    private LocalDateTime lastWaterAt;

    private Integer waterIntervalDays;

    private String photoUrl;

    private LocalDateTime createdAt;
}
