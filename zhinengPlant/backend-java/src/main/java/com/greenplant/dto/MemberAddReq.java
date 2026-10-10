package com.greenplant.dto;

import jakarta.validation.constraints.Pattern;

public record MemberAddReq(
        Long userId,

        @Pattern(regexp = "^1\\d{10}$", message = "手机号格式不正确")
        String phone,

        String role,
        String duty
) {
}
