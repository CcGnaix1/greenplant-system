package com.greenplant.entity;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class CareRecord {

    private Long id;

    private Long plantId;

    private Long userId;

    private String type;

    private String note;

    private LocalDateTime createdAt;
}
