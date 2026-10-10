package com.greenplant.controller;

import com.greenplant.common.Result;
import com.greenplant.service.DiagnosisService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.Map;

/** 图像识别与健康诊断接口层。 */
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class DiagnosisController {
    private final DiagnosisService diagnosisService;

    @PostMapping("/species/recognize")
    public Result<Map<String, Object>> recognize(@RequestParam("image") MultipartFile image) {
        return diagnosisService.recognize(image);
    }

    @PostMapping("/diagnosis")
    public Result<Map<String, Object>> diagnosis(@RequestParam("image") MultipartFile image,
                                                 @RequestParam(value = "plantId", required = false) Long plantId) {
        return diagnosisService.diagnosis(image, plantId);
    }

    @GetMapping("/diagnosis/{diagId}")
    public Result<Map<String, Object>> detail(@PathVariable Long diagId) {
        return diagnosisService.detail(diagId);
    }

    @PostMapping("/diagnosis/{diagId}/feedback")
    public Result<Map<String, Object>> feedback(@PathVariable Long diagId) {
        return diagnosisService.feedback(diagId);
    }
}
