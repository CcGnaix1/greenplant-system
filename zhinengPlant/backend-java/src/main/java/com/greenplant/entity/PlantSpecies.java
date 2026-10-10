package com.greenplant.entity;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class PlantSpecies {

    private Long id;

    private String name;

    private String latinName;

    /** JSON：光照/温度/湿度/浇水间隔 */
    private String envSnapshot;

    private LocalDateTime createdAt;
}
