package com.greenplant.controller;

import com.greenplant.common.Result;
import com.greenplant.dto.CareRecordReq;
import com.greenplant.dto.PlantCreateReq;
import com.greenplant.dto.PlantUpdateReq;
import com.greenplant.service.PlantService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/** 植物档案与养护接口层。 */
@RestController
@RequestMapping("/api/plants")
@RequiredArgsConstructor
public class PlantController {
    private final PlantService plantService;

    @GetMapping
    public Result<List<Map<String, Object>>> list() {
        return plantService.list();
    }

    @PostMapping
    public Result<Map<String, Object>> create(@Valid @RequestBody PlantCreateReq req) {
        return plantService.create(req);
    }

    @GetMapping("/{id}")
    public Result<Map<String, Object>> detail(@PathVariable Long id) {
        return plantService.detail(id);
    }

    @PutMapping("/{id}")
    public Result<Map<String, Object>> update(@PathVariable Long id, @RequestBody PlantUpdateReq req) {
        return plantService.update(id, req);
    }

    @DeleteMapping("/{id}")
    public Result<Map<String, Object>> delete(@PathVariable Long id) {
        return plantService.delete(id);
    }

    @PostMapping("/{id}/watering")
    public Result<Map<String, Object>> watering(@PathVariable Long id,
                                                @RequestBody(required = false) CareRecordReq req) {
        return plantService.watering(id, req);
    }

    @PostMapping("/{id}/records")
    public Result<Map<String, Object>> addRecord(@PathVariable Long id, @RequestBody CareRecordReq req) {
        return plantService.addRecord(id, req);
    }

    @GetMapping("/{id}/timeline")
    public Result<List<Map<String, Object>>> timeline(@PathVariable Long id) {
        return plantService.timeline(id);
    }

    @GetMapping("/{id}/stats")
    public Result<Map<String, Object>> stats(@PathVariable Long id) {
        return plantService.stats(id);
    }

    @GetMapping("/{id}/care-plan")
    public Result<List<Map<String, Object>>> carePlan(@PathVariable Long id) {
        return plantService.carePlan(id);
    }
}
