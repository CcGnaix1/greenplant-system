package com.greenplant.dto;

import jakarta.validation.constraints.NotBlank;

/** 微信小程序登录请求：code 由 wx.login() 获取。 */
public record WechatLoginReq(
        @NotBlank(message = "code不能为空") String code,
        String nickname
) {
}
