package com.greenplant.entity;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class FamilyGroup {

    private Long id;

    private String name;

    private Long ownerId;

    private String inviteCode;

    private LocalDateTime createdAt;
}
