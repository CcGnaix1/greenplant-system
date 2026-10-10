package com.greenplant.mapper;

import com.greenplant.entity.User;
import org.apache.ibatis.annotations.Param;

import java.util.Optional;

/** 用户账号数据访问：登录查询、微信账号查询以及账号新增/更新。 */
public interface UserMapper {
    Optional<User> findById(@Param("id") Long id);
    Optional<User> findByPhone(@Param("phone") String phone);
    Optional<User> findByOpenid(@Param("openid") String openid);
    int insert(User user);
    int update(User user);

    default User save(User user) {
        if (user.getId() == null) insert(user); else update(user);
        return user;
    }
}
