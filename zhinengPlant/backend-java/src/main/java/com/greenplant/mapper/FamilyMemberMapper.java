package com.greenplant.mapper;

import com.greenplant.entity.FamilyMember;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/** 家庭成员关系数据访问。 */
public interface FamilyMemberMapper {
    List<FamilyMember> findByFamilyIdOrderByIdAsc(@Param("familyId") Long familyId);
    boolean existsByFamilyIdAndUserId(@Param("familyId") Long familyId, @Param("userId") Long userId);
    boolean existsByUserId(@Param("userId") Long userId);
    int insert(FamilyMember member);
    int update(FamilyMember member);

    default FamilyMember save(FamilyMember member) {
        if (member.getId() == null) insert(member); else update(member);
        return member;
    }
}
