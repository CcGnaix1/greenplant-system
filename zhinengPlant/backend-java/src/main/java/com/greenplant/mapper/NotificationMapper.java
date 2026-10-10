package com.greenplant.mapper;

import com.greenplant.entity.Notification;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Optional;

/** 用户通知数据访问：未读列表与已读状态维护。 */
public interface NotificationMapper {
    Optional<Notification> findById(@Param("id") Long id);
    List<Notification> findByUserIdAndIsReadOrderByCreatedAtDesc(@Param("userId") Long userId,
                                                                 @Param("isRead") Integer isRead);
    int insert(Notification notification);
    int update(Notification notification);

    default Notification save(Notification notification) {
        if (notification.getId() == null) insert(notification); else update(notification);
        return notification;
    }
}
