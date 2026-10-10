package com.greenplant.controller;

import com.greenplant.common.Result;
import com.greenplant.service.UserProfileService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.Map;

/** 用户资料接口层。 */
@RestController
@RequestMapping("/api/user")
@RequiredArgsConstructor
public class UserProfileController {
    private final UserProfileService userProfileService;

    @PostMapping("/avatar")
    public Result<Map<String, String>> uploadAvatar(@RequestParam("avatar") MultipartFile avatar) {
        return userProfileService.uploadAvatar(avatar);
    }
}
