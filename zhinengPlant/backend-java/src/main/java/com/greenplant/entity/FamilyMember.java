package com.greenplant.entity;

import lombok.Data;

@Data
public class FamilyMember {

    private Long id;

    private Long familyId;

    private Long userId;

    private String role;

    private String duty;
}
