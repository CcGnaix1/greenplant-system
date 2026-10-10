package com.greenplant.entity;

import lombok.Data;

import java.time.LocalDate;
import java.time.LocalDateTime;

@Data
public class FamilyTask {

    private Long id;

    private Long familyId;

    private Long plantId;

    private String title;

    private Long assigneeId;

    private LocalDate due;

    private Integer done;

    private LocalDateTime createdAt;
}
