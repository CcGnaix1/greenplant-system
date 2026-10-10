package com.greenplant.mapper;

import com.greenplant.entity.DiagnosisRecord;
import org.apache.ibatis.annotations.Param;

import java.util.Optional;

/** AI 健康诊断历史数据访问。 */
public interface DiagnosisRecordMapper {
    Optional<DiagnosisRecord> findById(@Param("id") Long id);
    int insert(DiagnosisRecord record);
    int update(DiagnosisRecord record);

    default DiagnosisRecord save(DiagnosisRecord record) {
        if (record.getId() == null) insert(record); else update(record);
        return record;
    }
}
