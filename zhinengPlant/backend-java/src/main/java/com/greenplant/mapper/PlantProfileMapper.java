package com.greenplant.mapper;

import com.greenplant.entity.PlantProfile;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Optional;

/** 植物档案数据访问：按用户/主键查询以及档案增删改。 */
public interface PlantProfileMapper {
    Optional<PlantProfile> findById(@Param("id") Long id);
    List<PlantProfile> findByUserIdOrderByCreatedAtDesc(@Param("userId") Long userId);
    int insert(PlantProfile plant);
    int update(PlantProfile plant);
    int deleteById(@Param("id") Long id);

    default PlantProfile save(PlantProfile plant) {
        if (plant.getId() == null) insert(plant); else update(plant);
        return plant;
    }

    default void delete(PlantProfile plant) {
        deleteById(plant.getId());
    }
}
