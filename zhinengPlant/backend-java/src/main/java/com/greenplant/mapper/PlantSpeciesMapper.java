package com.greenplant.mapper;

import com.greenplant.entity.PlantSpecies;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Optional;

/** 植物品种基础数据访问。 */
public interface PlantSpeciesMapper {
    Optional<PlantSpecies> findById(@Param("id") Long id);
    List<PlantSpecies> findAll();
}
