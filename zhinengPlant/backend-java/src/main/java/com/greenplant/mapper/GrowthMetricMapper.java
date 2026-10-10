package com.greenplant.mapper;

import com.greenplant.entity.GrowthMetric;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/** 植物高度、叶片数量等生长指标数据访问。 */
public interface GrowthMetricMapper {
    List<GrowthMetric> findByPlantIdOrderByRecordedAtAsc(@Param("plantId") Long plantId);
}
