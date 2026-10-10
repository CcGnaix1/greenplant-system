package com.greenplant.entity;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class UserProfile {
    private Long userId;

    private String avatarUrl;

    private LocalDateTime updatedAt;
}
