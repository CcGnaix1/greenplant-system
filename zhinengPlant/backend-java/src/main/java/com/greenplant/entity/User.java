package com.greenplant.entity;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class User {

    private Long id;

    private String phone;

    private String passwordHash;

    private String nickname;

    private String openid;

    private Long familyId;

    private String role;

    private LocalDateTime createdAt;
}
