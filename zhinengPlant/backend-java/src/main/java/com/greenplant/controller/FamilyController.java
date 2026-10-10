package com.greenplant.controller;

import com.greenplant.common.Result;
import com.greenplant.dto.FamilyCreateReq;
import com.greenplant.dto.MemberAddReq;
import com.greenplant.dto.TaskAssignReq;
import com.greenplant.service.FamilyService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/** 家庭协作接口层。 */
@RestController
@RequestMapping("/api/family")
@RequiredArgsConstructor
public class FamilyController {
    private final FamilyService familyService;

    @PostMapping
    public Result<Map<String, Object>> create(@Valid @RequestBody FamilyCreateReq req) {
        return familyService.create(req);
    }

    @PostMapping("/{fid}/invite")
    public Result<Map<String, Object>> invite(@PathVariable Long fid) {
        return familyService.invite(fid);
    }

    @PostMapping("/{fid}/members")
    public Result<Map<String, Object>> addMember(@PathVariable Long fid, @Valid @RequestBody MemberAddReq req) {
        return familyService.addMember(fid, req);
    }

    @GetMapping("/{fid}/members")
    public Result<List<Map<String, Object>>> members(@PathVariable Long fid) {
        return familyService.members(fid);
    }

    @PostMapping("/{fid}/tasks")
    public Result<Map<String, Object>> assignTask(@PathVariable Long fid, @Valid @RequestBody TaskAssignReq req) {
        return familyService.assignTask(fid, req);
    }

    @GetMapping("/{fid}/tasks")
    public Result<List<Map<String, Object>>> tasks(@PathVariable Long fid,
                                                   @RequestParam(defaultValue = "all") String status,
                                                   @RequestParam(defaultValue = "false") boolean mine) {
        return familyService.tasks(fid, status, mine);
    }

    @PatchMapping("/tasks/{taskId}/complete")
    public Result<Map<String, Object>> completeTask(@PathVariable Long taskId) {
        return familyService.completeTask(taskId);
    }

    @PatchMapping("/tasks/{taskId}/done")
    public Result<Map<String, Object>> toggleDone(@PathVariable Long taskId) {
        return familyService.toggleDone(taskId);
    }
}
