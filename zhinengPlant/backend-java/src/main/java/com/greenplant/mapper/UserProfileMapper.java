package com.greenplant.mapper;

import com.greenplant.entity.UserProfile;
import org.apache.ibatis.annotations.Param;

import java.util.Optional;

/** 用户扩展资料数据访问，目前主要维护头像地址。 */
public interface UserProfileMapper {
    Optional<UserProfile> findById(@Param("userId") Long userId);
    int insert(UserProfile profile);
    int update(UserProfile profile);

    default UserProfile save(UserProfile profile) {
        if (update(profile) == 0) insert(profile);
        return profile;
    }
}
