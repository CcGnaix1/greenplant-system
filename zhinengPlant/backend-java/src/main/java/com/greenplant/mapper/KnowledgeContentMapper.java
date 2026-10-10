package com.greenplant.mapper;

import com.greenplant.entity.KnowledgeContent;
import org.apache.ibatis.annotations.Param;

import java.util.Optional;

/** 植物知识库内容数据访问。 */
public interface KnowledgeContentMapper {
    Optional<KnowledgeContent> findBySpeciesId(@Param("speciesId") Long speciesId);
}
