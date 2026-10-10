package com.greenplant.dto;

import jakarta.validation.constraints.NotBlank;

public record LoginReq(
        @NotBlank(message = "手机号不能为空") String phone,
        @NotBlank(message = "密码不能为空") String password
) {
}
