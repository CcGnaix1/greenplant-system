package com.greenplant.entity;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class DiagnosisRecord {

    private Long id;

    private Long plantId;

    private Long userId;

    /** JSON 症状多标签 */
    private String symptoms;

    /** JSON 诊断报告 */
    private String report;

    private Integer feedback;

    private LocalDateTime createdAt;
}
