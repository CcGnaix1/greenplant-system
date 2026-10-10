package com.greenplant.controller;

import com.greenplant.common.Result;
import com.greenplant.service.ExportService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/** 数据导出接口层。 */
@RestController
@RequestMapping("/api/export")
@RequiredArgsConstructor
public class ExportController {
    private final ExportService exportService;

    @GetMapping("/plant/{plantId}")
    public Result<Map<String, Object>> exportPlant(@PathVariable Long plantId,
                                                   @RequestParam(defaultValue = "pdf") String format) {
        return exportService.exportPlant(plantId, format);
    }

    @GetMapping("/records")
    public Result<Map<String, Object>> exportRecords(@RequestParam(defaultValue = "excel") String format,
                                                     @RequestParam(defaultValue = "") String start,
                                                     @RequestParam(defaultValue = "") String end) {
        return exportService.exportRecords(format, start, end);
    }
}
