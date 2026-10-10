package com.greenplant.dto;

import jakarta.validation.constraints.NotBlank;

import java.time.LocalDate;

public record TaskAssignReq(
        Long plantId,
        @NotBlank(message = "任务标题不能为空") String title,
        Long assigneeId,
        LocalDate due
) {
}
