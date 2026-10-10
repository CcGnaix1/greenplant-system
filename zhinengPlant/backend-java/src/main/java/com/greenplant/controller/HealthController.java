package com.greenplant.controller;

import com.greenplant.common.Result;
import com.greenplant.service.HealthService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class HealthController {
    private final HealthService healthService;

    @GetMapping("/health")
    public Result<Map<String, Object>> health() {
        return healthService.health();
    }
}
