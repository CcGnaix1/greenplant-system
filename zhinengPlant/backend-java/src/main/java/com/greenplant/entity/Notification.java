package com.greenplant.entity;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class Notification {

    private Long id;

    private Long userId;

    private String title;

    private Integer isRead;

    private LocalDateTime createdAt;
}
