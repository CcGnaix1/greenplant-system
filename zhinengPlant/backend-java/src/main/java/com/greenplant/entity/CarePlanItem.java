package com.greenplant.entity;

import lombok.Data;

import java.time.LocalDate;
import java.time.LocalDateTime;

@Data
public class CarePlanItem {

    private Long id;

    private Long plantId;

    private String taskType;

    private LocalDate dueDate;

    private Integer done;

    private LocalDateTime createdAt;
}
