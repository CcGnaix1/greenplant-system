package com.greenplant.mapper;

import com.greenplant.entity.FamilyTask;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Optional;

/** 家庭养护任务数据访问。 */
public interface FamilyTaskMapper {
    Optional<FamilyTask> findById(@Param("id") Long id);
    List<FamilyTask> findByFamilyIdOrderByIdDesc(@Param("familyId") Long familyId);
    int insert(FamilyTask task);
    int update(FamilyTask task);

    default FamilyTask save(FamilyTask task) {
        if (task.getId() == null) insert(task); else update(task);
        return task;
    }
}
