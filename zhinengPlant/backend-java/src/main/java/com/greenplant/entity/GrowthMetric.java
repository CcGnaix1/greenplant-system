package com.greenplant.entity;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class GrowthMetric {

    private Long id;

    private Long plantId;

    private java.math.BigDecimal heightCm;

    private Integer leafCount;

    private LocalDateTime recordedAt;
}
