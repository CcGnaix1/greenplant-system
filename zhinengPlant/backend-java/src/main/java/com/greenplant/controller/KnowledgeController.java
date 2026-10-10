package com.greenplant.controller;

import com.greenplant.common.Result;
import com.greenplant.service.KnowledgeService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/** 知识库与通知接口层。 */
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class KnowledgeController {
    private final KnowledgeService knowledgeService;

    @GetMapping("/knowledge/species/{speciesId}")
    public Result<Map<String, Object>> speciesKnowledge(@PathVariable Long speciesId) {
        return knowledgeService.speciesKnowledge(speciesId);
    }

    @GetMapping("/knowledge/search")
    public Result<List<Map<String, Object>>> search(@RequestParam(defaultValue = "") String keyword) {
        return knowledgeService.search(keyword);
    }

    @GetMapping("/notifications")
    public Result<List<Map<String, Object>>> notifications(@RequestParam(defaultValue = "0") int isRead) {
        return knowledgeService.notifications(isRead);
    }

    @PatchMapping("/notifications/{nid}/read")
    public Result<Map<String, Object>> markRead(@PathVariable Long nid) {
        return knowledgeService.markRead(nid);
    }
}
