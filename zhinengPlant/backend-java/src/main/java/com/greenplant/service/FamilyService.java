package com.greenplant.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import com.greenplant.common.BizException;
import com.greenplant.common.Result;
import com.greenplant.common.UserContext;
import com.greenplant.dto.FamilyCreateReq;
import com.greenplant.dto.MemberAddReq;
import com.greenplant.dto.TaskAssignReq;
import com.greenplant.entity.FamilyGroup;
import com.greenplant.entity.FamilyMember;
import com.greenplant.entity.FamilyTask;
import com.greenplant.entity.User;
import com.greenplant.mapper.FamilyGroupMapper;
import com.greenplant.mapper.FamilyMemberMapper;
import com.greenplant.mapper.FamilyTaskMapper;
import com.greenplant.mapper.PlantProfileMapper;
import com.greenplant.mapper.UserMapper;
import lombok.RequiredArgsConstructor;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
/** 家庭协作业务：家庭创建、成员管理、任务分配以及任务完成状态同步。 */
public class FamilyService {

    private final FamilyGroupMapper groupMapper;
    private final FamilyMemberMapper memberMapper;
    private final FamilyTaskMapper taskMapper;
    private final UserMapper userMapper;
    private final PlantProfileMapper plantMapper;

    /** 创建家庭组，同时将当前用户设置为家庭管理员。 */
    @Transactional
    public Result<Map<String, Object>> create(FamilyCreateReq req) {
        Long uid = UserContext.get();
        if (memberMapper.existsByUserId(uid)) {
            throw new BizException(4000, "你已经加入家庭组，不能重复创建");
        }
        FamilyGroup g = new FamilyGroup();
        g.setName(req.name());
        g.setOwnerId(uid);
        g.setInviteCode("invite_" + uid);
        g.setCreatedAt(LocalDateTime.now());
        groupMapper.save(g);

        FamilyMember me = new FamilyMember();
        me.setFamilyId(g.getId());
        me.setUserId(uid);
        me.setRole("owner");
        me.setDuty("管理员");
        memberMapper.save(me);

        userMapper.findById(uid).ifPresent(u -> {
            u.setFamilyId(g.getId());
            u.setRole("owner");
            userMapper.save(u);
        });

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("familyId", g.getId());
        data.put("inviteCode", g.getInviteCode());
        return Result.ok(data);
    }

    /** 仅管理员可获取家庭邀请码。 */
    public Result<Map<String, Object>> invite(Long fid) {
        FamilyGroup g = requireOwner(fid);
        return Result.ok(Map.of("inviteCode", g.getInviteCode()));
    }

    /** 管理员按手机号或用户编号添加已注册成员。 */
    @Transactional
    public Result<Map<String, Object>> addMember(Long fid, MemberAddReq req) {
        requireOwner(fid);
        User target;
        if (req.userId() != null) {
            target = userMapper.findById(req.userId())
                    .orElseThrow(() -> new BizException(4040, "待添加用户不存在"));
        } else if (req.phone() != null && !req.phone().isBlank()) {
            target = userMapper.findByPhone(req.phone().trim())
                    .orElseThrow(() -> new BizException(4040, "该手机号尚未注册，请先使用手机号注册"));
        } else {
            throw new BizException(4000, "请输入成员手机号");
        }
        if (memberMapper.existsByUserId(target.getId())) {
            throw new BizException(4000, "该用户已经加入家庭组");
        }
        FamilyMember m = new FamilyMember();
        m.setFamilyId(fid);
        m.setUserId(target.getId());
        m.setRole("member");
        m.setDuty(req.duty() == null || req.duty().isBlank() ? "共同养护" : req.duty().trim());
        memberMapper.save(m);
        target.setFamilyId(fid);
        target.setRole(m.getRole());
        userMapper.save(target);

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("userId", target.getId());
        data.put("nickname", target.getNickname());
        return Result.ok("成员添加成功", data);
    }

    /** 查询家庭成员，并对手机号进行脱敏显示。 */
    public Result<List<Map<String, Object>>> members(Long fid) {
        requireMember(fid);
        List<Map<String, Object>> data = new ArrayList<>();
        memberMapper.findByFamilyIdOrderByIdAsc(fid).forEach(m -> {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", m.getId());
            item.put("userId", m.getUserId());
            User user = userMapper.findById(m.getUserId()).orElse(null);
            item.put("name", user == null ? "用户" + m.getUserId() : user.getNickname());
            item.put("phone", user == null ? "" : maskPhone(user.getPhone()));
            item.put("role", m.getRole());
            item.put("duty", m.getDuty());
            data.add(item);
        });
        return Result.ok(data);
    }

    /** 为家庭成员的植物分配养护任务。 */
    @Transactional
    public Result<Map<String, Object>> assignTask(Long fid, TaskAssignReq req) {
        requireMember(fid);
        if (req.assigneeId() == null || !memberMapper.existsByFamilyIdAndUserId(fid, req.assigneeId())) {
            throw new BizException(4000, "任务执行人不是该家庭成员");
        }
        if (req.plantId() == null) {
            throw new BizException(4000, "请选择植物");
        }
        var plant = plantMapper.findById(req.plantId())
                .orElseThrow(() -> new BizException(4040, "植物不存在"));
        if (!memberMapper.existsByFamilyIdAndUserId(fid, plant.getUserId())) {
            throw new BizException(4030, "只能为本家庭成员的植物分配任务");
        }
        FamilyTask t = new FamilyTask();
        t.setFamilyId(fid);
        t.setPlantId(req.plantId());
        t.setTitle(req.title());
        t.setAssigneeId(req.assigneeId());
        t.setDue(req.due());
        t.setDone(0);
        t.setCreatedAt(LocalDateTime.now());
        taskMapper.save(t);
        return Result.ok(Map.of("taskId", t.getId()));
    }

    /** 查询家庭任务，可筛选待办状态和只看分配给自己的任务。 */
    public Result<List<Map<String, Object>>> tasks(Long fid,
                                                   String status,
                                                   boolean mine) {
        requireMember(fid);
        Long currentUserId = UserContext.get();
        List<FamilyTask> tasks = taskMapper.findByFamilyIdOrderByIdDesc(fid).stream()
                .filter(t -> !mine || currentUserId.equals(t.getAssigneeId()))
                .filter(t -> !"todo".equals(status) || t.getDone() == null || t.getDone() == 0)
                .toList();
        String familyName = groupMapper.findById(fid).map(FamilyGroup::getName).orElse("我的家庭");
        List<Map<String, Object>> data = new ArrayList<>();
        tasks.forEach(t -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", t.getId());
            m.put("title", t.getTitle());
            m.put("familyName", familyName);
            m.put("plantId", t.getPlantId());
            m.put("plant", t.getPlantId() == null ? "" : plantMapper.findById(t.getPlantId())
                    .map(p -> p.getName()).orElse("植物#" + t.getPlantId()));
            m.put("assigneeId", t.getAssigneeId());
            m.put("assignee", t.getAssigneeId() == null ? "" :
                    userMapper.findById(t.getAssigneeId()).map(User::getNickname).orElse("用户" + t.getAssigneeId()));
            m.put("due", t.getDue() == null ? null : t.getDue().toString());
            m.put("overdue", t.getDue() != null && t.getDue().isBefore(java.time.LocalDate.now())
                    && (t.getDone() == null || t.getDone() == 0));
            m.put("done", t.getDone() != null && t.getDone() == 1);
            data.add(m);
        });
        return Result.ok(data);
    }

    /** 执行人或管理员完成任务，首页和家庭协作页会读取同一状态。 */
    @Transactional
    public Result<Map<String, Object>> completeTask(Long taskId) {
        FamilyTask task = taskMapper.findById(taskId)
                .orElseThrow(() -> new BizException(4040, "任务不存在"));
        requireMember(task.getFamilyId());
        FamilyGroup group = groupMapper.findById(task.getFamilyId())
                .orElseThrow(() -> new BizException(4040, "家庭组不存在"));
        Long currentUserId = UserContext.get();
        boolean canComplete = currentUserId.equals(task.getAssigneeId()) || currentUserId.equals(group.getOwnerId());
        if (!canComplete) {
            throw new BizException(4030, "只能完成分配给自己的任务");
        }
        task.setDone(1);
        taskMapper.save(task);
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("taskId", taskId);
        data.put("done", true);
        return Result.ok("任务已完成", data);
    }

    /** 在已完成和未完成之间切换任务状态。 */
    @Transactional
    public Result<Map<String, Object>> toggleDone(Long taskId) {
        FamilyTask t = taskMapper.findById(taskId)
                .orElseThrow(() -> new BizException(4040, "任务不存在"));
        requireMember(t.getFamilyId());
        t.setDone(t.getDone() != null && t.getDone() == 1 ? 0 : 1);
        taskMapper.save(t);
        return Result.ok(Map.of("taskId", taskId));
    }

    /** 校验家庭存在且当前用户属于该家庭。 */
    private void requireMember(Long familyId) {
        if (!groupMapper.existsById(familyId)) {
            throw new BizException(4040, "家庭组不存在");
        }
        if (!memberMapper.existsByFamilyIdAndUserId(familyId, UserContext.get())) {
            throw new BizException(4030, "无权访问该家庭组");
        }
    }

    /** 校验当前用户是否为家庭管理员。 */
    private FamilyGroup requireOwner(Long familyId) {
        FamilyGroup group = groupMapper.findById(familyId)
                .orElseThrow(() -> new BizException(4040, "家庭组不存在"));
        if (!group.getOwnerId().equals(UserContext.get())) {
            throw new BizException(4030, "仅家庭管理员可执行该操作");
        }
        return group;
    }

    private String maskPhone(String phone) {
        if (phone == null || phone.length() != 11) {
            return "";
        }
        return phone.substring(0, 3) + "****" + phone.substring(7);
    }
}
