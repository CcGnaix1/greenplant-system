package com.greenplant.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.greenplant.common.BizException;
import com.greenplant.common.Result;
import com.greenplant.common.UserContext;
import com.greenplant.entity.KnowledgeContent;
import com.greenplant.entity.Notification;
import com.greenplant.entity.PlantSpecies;
import com.greenplant.mapper.KnowledgeContentMapper;
import com.greenplant.mapper.NotificationMapper;
import com.greenplant.mapper.PlantSpeciesMapper;
import lombok.RequiredArgsConstructor;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
/** 知识库与消息业务：植物养护知识检索、通知列表和已读状态维护。 */
public class KnowledgeService {

    private static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final KnowledgeContentMapper knowledgeMapper;
    private final PlantSpeciesMapper speciesMapper;
    private final NotificationMapper notificationMapper;
    private final ObjectMapper mapper = new ObjectMapper();

    /** 根据植物品种编号返回习性、四季养护、繁殖方法和常见问题。 */
    public Result<Map<String, Object>> speciesKnowledge(Long speciesId) {
        KnowledgeContent k = knowledgeMapper.findBySpeciesId(speciesId)
                .orElseThrow(() -> new BizException(4040, "暂无该品种知识"));
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("speciesId", speciesId);
        data.put("habit", k.getHabit());
        data.put("seasons", split(k.getSeasons()));
        data.put("water", k.getWater());
        data.put("fertilize", k.getFertilize());
        data.put("breed", k.getBreed());
        data.put("faq", parseJsonList(k.getFaq()));
        return Result.ok(data);
    }

    /** 按品种名称或习性关键字搜索知识库。 */
    public Result<List<Map<String, Object>>> search(String keyword) {
        List<Map<String, Object>> data = new ArrayList<>();
        speciesMapper.findAll().forEach(sp -> {
            KnowledgeContent k = knowledgeMapper.findBySpeciesId(sp.getId()).orElse(null);
            String habit = k == null ? "" : (k.getHabit() == null ? "" : k.getHabit());
            if (keyword.isBlank() || sp.getName().contains(keyword) || habit.contains(keyword)) {
                Map<String, Object> m = new LinkedHashMap<>();
                m.put("id", sp.getId());
                m.put("name", sp.getName());
                m.put("desc", habit.length() > 30 ? habit.substring(0, 30) : habit);
                data.add(m);
            }
        });
        return Result.ok(data);
    }

    /** 查询当前用户指定已读状态的通知。 */
    public Result<List<Map<String, Object>>> notifications(int isRead) {
        List<Map<String, Object>> data = new ArrayList<>();
        notificationMapper.findByUserIdAndIsReadOrderByCreatedAtDesc(com.greenplant.common.UserContext.get(), isRead)
                .forEach(n -> {
                    Map<String, Object> m = new LinkedHashMap<>();
                    m.put("id", n.getId());
                    m.put("title", n.getTitle());
                    m.put("time", n.getCreatedAt() == null ? null : n.getCreatedAt().format(FMT));
                    m.put("read", n.getIsRead() != null && n.getIsRead() == 1);
                    data.add(m);
                });
        return Result.ok(data);
    }

    /** 校验通知归属后，将通知设置为已读。 */
    @Transactional
    public Result<Map<String, Object>> markRead(Long nid) {
        Notification n = notificationMapper.findById(nid)
                .orElseThrow(() -> new BizException(4040, "通知不存在"));
        if (!n.getUserId().equals(UserContext.get())) {
            throw new BizException(4030, "无权操作该通知");
        }
        n.setIsRead(1);
        notificationMapper.save(n);
        return Result.ok(Map.of("id", nid));
    }

    private List<String> split(String s) {
        List<String> out = new ArrayList<>();
        if (s != null) {
            for (String part : s.split(";")) {
                if (!part.isBlank()) out.add(part.trim());
            }
        }
        return out;
    }

    private List<Map<String, Object>> parseJsonList(String json) {
        try {
            if (json == null || json.isBlank()) return List.of();
            return mapper.readValue(json, new TypeReference<List<Map<String, Object>>>() {
            });
        } catch (Exception e) {
            return List.of();
        }
    }
}
