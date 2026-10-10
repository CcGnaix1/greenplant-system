package com.greenplant.entity;

import lombok.Data;

@Data
public class KnowledgeContent {

    private Long id;

    private Long speciesId;

    private String habit;

    /** 分号分隔 */
    private String seasons;

    private String water;

    private String fertilize;

    private String breed;

    /** JSON FAQ */
    private String faq;
}
