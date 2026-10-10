package com.greenplant.controller;

import com.greenplant.common.Result;
import com.greenplant.dto.LoginReq;
import com.greenplant.dto.RegisterReq;
import com.greenplant.dto.WechatLoginReq;
import com.greenplant.service.AuthService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/** 认证接口层：只处理 HTTP 参数，业务逻辑交给 Service。 */
@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {
    private final AuthService authService;

    @PostMapping("/register")
    public Result<Map<String, Object>> register(@Valid @RequestBody RegisterReq req) {
        return authService.register(req);
    }

    @PostMapping("/login")
    public Result<Map<String, Object>> login(@Valid @RequestBody LoginReq req) {
        return authService.login(req);
    }

    @PostMapping("/wechat")
    public Result<Map<String, Object>> wechat(@Valid @RequestBody WechatLoginReq req) {
        return authService.wechat(req);
    }
}
