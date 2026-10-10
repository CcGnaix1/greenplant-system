package com.greenplant.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.greenplant.common.BizException;
import com.greenplant.common.Result;
import com.greenplant.common.UserContext;
import com.greenplant.dto.CareRecordReq;
import com.greenplant.dto.PlantCreateReq;
import com.greenplant.dto.PlantUpdateReq;
import com.greenplant.entity.CarePlanItem;
import com.greenplant.entity.CareRecord;
import com.greenplant.entity.GrowthMetric;
import com.greenplant.entity.PlantProfile;
import com.greenplant.entity.PlantSpecies;
import com.greenplant.mapper.CarePlanItemMapper;
import com.greenplant.mapper.CareRecordMapper;
import com.greenplant.mapper.GrowthMetricMapper;
import com.greenplant.mapper.PlantProfileMapper;
import com.greenplant.mapper.PlantSpeciesMapper;
import lombok.RequiredArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
/** 植物核心业务：档案管理、浇水记录、养护时间轴、统计与养护计划。 */
public class PlantService {

    private static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final PlantProfileMapper plantMapper;
    private final PlantSpeciesMapper speciesMapper;
    private final CareRecordMapper recordMapper;
    private final CarePlanItemMapper planMapper;
    private final GrowthMetricMapper metricMapper;
    private final ObjectMapper mapper = new ObjectMapper();

    private Long uid() {
        return UserContext.get();
    }

    /** 查询植物并校验它属于当前登录用户，防止越权访问。 */
    private PlantProfile own(Long id) {
        PlantProfile p = plantMapper.findById(id)
                .orElseThrow(() -> new BizException(4040, "植物不存在"));
        if (!p.getUserId().equals(uid())) {
            throw new BizException(4030, "无权访问该植物");
        }
        return p;
    }

    /** 将品种表中的环境 JSON 转为前端可直接使用的对象。 */
    private Map<String, Object> envOf(PlantSpecies sp) {
        Map<String, Object> env = new LinkedHashMap<>();
        if (sp != null && sp.getEnvSnapshot() != null) {
            try {
                env = mapper.readValue(sp.getEnvSnapshot(), new TypeReference<Map<String, Object>>() {
                });
            } catch (Exception ignored) {
            }
        }
        return env;
    }

    /** 返回当前用户的全部植物及品种、养护次数和最后浇水时间。 */
    public Result<List<Map<String, Object>>> list() {
        List<PlantProfile> plants = plantMapper.findByUserIdOrderByCreatedAtDesc(uid());
        Map<Long, String> speciesName = speciesMapper.findAll().stream()
                .collect(Collectors.toMap(PlantSpecies::getId, PlantSpecies::getName));
        List<Map<String, Object>> data = plants.stream().map(p -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", p.getId());
            m.put("name", p.getName());
            m.put("species", speciesName.getOrDefault(p.getSpeciesId(), "未知品种"));
            m.put("tag", p.getEmotionTag());
            m.put("status", p.getStatus());
            m.put("heightCm", p.getInitHeightCm());
            m.put("recordCount", recordMapper.countByPlantId(p.getId()));
            m.put("lastWaterAt", p.getLastWaterAt() == null ? null : p.getLastWaterAt().format(FMT));
            m.put("photoUrl", p.getPhotoUrl());
            return m;
        }).collect(Collectors.toList());
        return Result.ok(data);
    }

    /** 创建植物档案，并同步生成首个默认浇水计划。 */
    @Transactional
    public Result<Map<String, Object>> create(PlantCreateReq req) {
        PlantSpecies sp = speciesMapper.findById(req.speciesId())
                .orElseThrow(() -> new BizException(4040, "品种不存在"));
        PlantProfile p = new PlantProfile();
        p.setUserId(uid());
        p.setSpeciesId(req.speciesId());
        p.setName(req.name());
        p.setPotMaterial(req.potMaterial());
        p.setInitHeightCm(req.initHeightCm() == null ? BigDecimal.ZERO : req.initHeightCm());
        p.setEmotionTag(req.emotionTag());
        p.setStatus("ok");
        p.setWaterIntervalDays(3);
        p.setCreatedAt(LocalDateTime.now());
        plantMapper.save(p);

        // 建档即生成默认养护计划（浇水任务）
        CarePlanItem item = new CarePlanItem();
        item.setPlantId(p.getId());
        item.setTaskType("watering");
        item.setDueDate(LocalDate.now().plusDays(3));
        item.setDone(0);
        planMapper.save(item);

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("id", p.getId());
        data.put("env", envOf(sp));
        data.put("message", "建档成功，已生成默认养护计划");
        return Result.ok(data);
    }

    /** 查询植物档案详情和适宜生长环境。 */
    public Result<Map<String, Object>> detail(Long id) {
        PlantProfile p = own(id);
        PlantSpecies sp = speciesMapper.findById(p.getSpeciesId()).orElse(null);
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("id", p.getId());
        data.put("name", p.getName());
        data.put("species", sp == null ? "未知品种" : sp.getName());
        data.put("speciesId", p.getSpeciesId());
        data.put("potMaterial", p.getPotMaterial());
        data.put("heightCm", p.getInitHeightCm());
        data.put("emotionTag", p.getEmotionTag());
        data.put("status", p.getStatus());
        data.put("lastWaterAt", p.getLastWaterAt() == null ? null : p.getLastWaterAt().format(FMT));
        data.put("env", envOf(sp));
        data.put("createdAt", p.getCreatedAt() == null ? null : p.getCreatedAt().format(FMT));
        return Result.ok(data);
    }

    /** 按前端提交的非空字段更新植物档案。 */
    @Transactional
    public Result<Map<String, Object>> update(Long id, PlantUpdateReq req) {
        PlantProfile p = own(id);
        if (req.name() != null) p.setName(req.name());
        if (req.potMaterial() != null) p.setPotMaterial(req.potMaterial());
        if (req.initHeightCm() != null) p.setInitHeightCm(req.initHeightCm());
        if (req.emotionTag() != null) p.setEmotionTag(req.emotionTag());
        if (req.status() != null) p.setStatus(req.status());
        plantMapper.save(p);
        return Result.ok(Map.of("id", p.getId()));
    }

    /** 校验归属后删除指定植物档案。 */
    @Transactional
    public Result<Map<String, Object>> delete(Long id) {
        PlantProfile p = own(id);
        plantMapper.delete(p);
        return Result.ok(Map.of("deleted", id));
    }

    /** 完成一次浇水：更新最后浇水时间、保存记录并生成下次计划。 */
    @Transactional
    public Result<Map<String, Object>> watering(Long id, CareRecordReq req) {
        PlantProfile p = own(id);
        LocalDateTime now = LocalDateTime.now();
        p.setLastWaterAt(now);
        plantMapper.save(p);

        CareRecord r = new CareRecord();
        r.setPlantId(id);
        r.setUserId(uid());
        r.setType("water");
        r.setNote(req == null || req.note() == null ? "" : req.note());
        r.setCreatedAt(now);
        recordMapper.save(r);

        int interval = p.getWaterIntervalDays() == null ? 3 : p.getWaterIntervalDays();
        CarePlanItem item = new CarePlanItem();
        item.setPlantId(id);
        item.setTaskType("watering");
        item.setDueDate(now.toLocalDate().plusDays(interval));
        item.setDone(0);
        planMapper.save(item);

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("careRecordId", r.getId());
        data.put("opTime", now.format(FMT));
        data.put("nextDueDate", item.getDueDate().toString());
        return Result.ok(data);
    }

    /** 新增施肥、修剪、换盆等通用养护记录。 */
    @Transactional
    public Result<Map<String, Object>> addRecord(Long id, CareRecordReq req) {
        own(id);
        CareRecord r = new CareRecord();
        r.setPlantId(id);
        r.setUserId(uid());
        r.setType(req.type() == null ? "other" : req.type());
        r.setNote(req.note());
        r.setCreatedAt(LocalDateTime.now());
        recordMapper.save(r);
        return Result.ok(Map.of("careRecordId", r.getId()));
    }

    /** 按时间倒序返回植物的全部养护记录。 */
    public Result<List<Map<String, Object>>> timeline(Long id) {
        own(id);
        List<Map<String, Object>> data = new ArrayList<>();
        recordMapper.findByPlantIdOrderByCreatedAtDesc(id).forEach(r -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("type", r.getType());
            m.put("text", typeText(r.getType()));
            m.put("note", r.getNote());
            m.put("member", "我");
            m.put("time", r.getCreatedAt() == null ? null : r.getCreatedAt().format(FMT));
            data.add(m);
        });
        return Result.ok(data);
    }

    private String typeText(String type) {
        return switch (type == null ? "" : type) {
            case "water" -> "浇水";
            case "fertilize" -> "施肥";
            case "prune" -> "修剪";
            case "repot" -> "换盆";
            default -> "养护记录";
        };
    }

    /** 汇总浇水次数、记录数、距上次浇水天数和生长指标。 */
    public Result<Map<String, Object>> stats(Long id) {
        PlantProfile p = own(id);
        long waterCount = recordMapper.findByPlantIdOrderByCreatedAtDesc(id).stream()
                .filter(r -> "water".equals(r.getType())).count();
        long total = recordMapper.countByPlantId(id);
        long days = p.getLastWaterAt() == null ? -1 : ChronoUnit.DAYS.between(p.getLastWaterAt().toLocalDate(), LocalDate.now());
        List<GrowthMetric> metrics = metricMapper.findByPlantIdOrderByRecordedAtAsc(id);

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("recordCount", total);
        data.put("waterCount", waterCount);
        data.put("daysSinceWater", days);
        data.put("currentHeightCm", p.getInitHeightCm());
        data.put("growth", metrics.stream().map(g -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("date", g.getRecordedAt() == null ? null : g.getRecordedAt().format(FMT));
            m.put("heightCm", g.getHeightCm());
            m.put("leafCount", g.getLeafCount());
            return m;
        }).collect(Collectors.toList()));
        return Result.ok(data);
    }

    /** 返回未完成养护计划；没有计划时根据浇水周期生成展示建议。 */
    public Result<List<Map<String, Object>>> carePlan(Long id) {
        PlantProfile p = own(id);
        PlantSpecies sp = speciesMapper.findById(p.getSpeciesId()).orElse(null);
        Map<String, Object> env = envOf(sp);
        long dryDays = p.getLastWaterAt() == null ? 0
                : Math.max(0, ChronoUnit.DAYS.between(p.getLastWaterAt().toLocalDate(), LocalDate.now()));

        List<Map<String, Object>> data = new ArrayList<>();
        List<CarePlanItem> items = planMapper.findByPlantIdAndDoneOrderByDueDateAsc(id, 0);
        for (CarePlanItem it : items) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("taskType", it.getTaskType());
            m.put("plantName", p.getName());
            m.put("habit", env.getOrDefault("light", "散射光"));
            m.put("dryDays", dryDays);
            m.put("suggestion", ("water".equals(it.getTaskType()) || "watering".equals(it.getTaskType()))
                    ? "建议在傍晚浇透水" : "按计划执行");
            m.put("lastDoneAt", p.getLastWaterAt() == null ? "-" : p.getLastWaterAt().format(FMT));
            m.put("nextDueDate", it.getDueDate() == null ? null : it.getDueDate().toString());
            data.add(m);
        }
        if (data.isEmpty()) {
            int interval = p.getWaterIntervalDays() == null ? 3 : p.getWaterIntervalDays();
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("taskType", "watering");
            m.put("plantName", p.getName());
            m.put("habit", env.getOrDefault("light", "散射光"));
            m.put("dryDays", dryDays);
            m.put("suggestion", "建议在傍晚浇透水");
            m.put("lastDoneAt", p.getLastWaterAt() == null ? "-" : p.getLastWaterAt().format(FMT));
            m.put("nextDueDate", LocalDate.now().plusDays(interval).toString());
            data.add(m);
        }
        return Result.ok(data);
    }
}
