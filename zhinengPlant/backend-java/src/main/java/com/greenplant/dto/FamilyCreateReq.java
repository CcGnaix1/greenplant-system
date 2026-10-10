package com.greenplant.dto;

import jakarta.validation.constraints.NotBlank;

public record FamilyCreateReq(
        @NotBlank(message = "家庭组名称不能为空") String name
) {
}
