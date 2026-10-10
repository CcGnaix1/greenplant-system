package com.greenplant.mapper;

import com.greenplant.entity.CarePlanItem;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/** 植物养护计划数据访问。 */
public interface CarePlanItemMapper {
    List<CarePlanItem> findByPlantIdAndDoneOrderByDueDateAsc(@Param("plantId") Long plantId,
                                                             @Param("done") Integer done);
    int insert(CarePlanItem item);
    int update(CarePlanItem item);

    default CarePlanItem save(CarePlanItem item) {
        if (item.getId() == null) insert(item); else update(item);
        return item;
    }
}
