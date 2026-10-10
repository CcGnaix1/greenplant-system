package com.greenplant.mapper;

import com.greenplant.entity.CareRecord;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/** 养护记录数据访问：时间轴、用户导出和记录统计。 */
public interface CareRecordMapper {
    List<CareRecord> findByPlantIdOrderByCreatedAtDesc(@Param("plantId") Long plantId);
    List<CareRecord> findByUserIdOrderByCreatedAtDesc(@Param("userId") Long userId);
    long countByPlantId(@Param("plantId") Long plantId);
    int insert(CareRecord record);
    int update(CareRecord record);

    default CareRecord save(CareRecord record) {
        if (record.getId() == null) insert(record); else update(record);
        return record;
    }
}
