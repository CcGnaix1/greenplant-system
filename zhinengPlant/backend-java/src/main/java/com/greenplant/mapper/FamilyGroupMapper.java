package com.greenplant.mapper;

import com.greenplant.entity.FamilyGroup;
import org.apache.ibatis.annotations.Param;

import java.util.Optional;

/** 家庭组数据访问。 */
public interface FamilyGroupMapper {
    Optional<FamilyGroup> findById(@Param("id") Long id);
    boolean existsById(@Param("id") Long id);
    int insert(FamilyGroup group);
    int update(FamilyGroup group);

    default FamilyGroup save(FamilyGroup group) {
        if (group.getId() == null) insert(group); else update(group);
        return group;
    }
}
