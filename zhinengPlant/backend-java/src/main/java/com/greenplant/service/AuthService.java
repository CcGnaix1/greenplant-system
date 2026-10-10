package com.greenplant.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.greenplant.common.BizException;
import com.greenplant.common.JwtUtil;
import com.greenplant.common.PasswordUtil;
import com.greenplant.common.Result;
import com.greenplant.dto.LoginReq;
import com.greenplant.dto.RegisterReq;
import com.greenplant.dto.WechatLoginReq;
import com.greenplant.entity.User;
import com.greenplant.mapper.UserMapper;
import com.greenplant.mapper.UserProfileMapper;
import lombok.extern.slf4j.Slf4j;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.client.RestClient;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.Map;

@Service
@RequiredArgsConstructor
@Slf4j
/** 认证业务：处理手机号注册登录、微信 code 换取 openid，以及 JWT 登录信息生成。 */
public class AuthService {

    private final UserMapper userMapper;
    private final UserProfileMapper userProfileMapper;
    private final JwtUtil jwtUtil;
    private final ObjectMapper objectMapper;

    @Value("${sky.wechat.appid}")
    private String wechatAppId;

    @Value("${sky.wechat.secret}")
    private String wechatAppSecret;

    private final RestClient wechatClient = RestClient.create("https://api.weixin.qq.com");

    /** 注册手机号账号；校验号码唯一性，保存密码摘要并直接签发登录令牌。 */
    @Transactional
    public Result<Map<String, Object>> register(RegisterReq req) {
        userMapper.findByPhone(req.phone()).ifPresent(u -> {
            throw new BizException(4001, "该手机号已注册，请直接登录");
        });
        User user = new User();
        user.setPhone(req.phone());
        user.setPasswordHash(PasswordUtil.hash(req.password()));
        user.setNickname(req.nickname() == null || req.nickname().isBlank() ? "绿植主人" : req.nickname());
        user.setFamilyId(0L);
        user.setRole("owner");
        user.setCreatedAt(LocalDateTime.now());
        userMapper.save(user);

        return Result.ok("注册成功", loginData(user));
    }

    /** 校验手机号与密码摘要，成功后返回 JWT 和当前用户资料。 */
    public Result<Map<String, Object>> login(LoginReq req) {
        User user = userMapper.findByPhone(req.phone())
                .orElseThrow(() -> new BizException(4010, "手机号或密码错误"));
        if (!PasswordUtil.hash(req.password()).equals(user.getPasswordHash())) {
            throw new BizException(4010, "手机号或密码错误");
        }
        return Result.ok(loginData(user));
    }

    /** 调用微信 code2session，按 openid 查询或创建用户并返回登录令牌。 */
    @Transactional
    public Result<Map<String, Object>> wechat(WechatLoginReq req) {
        if (wechatAppId == null || wechatAppId.isBlank() || wechatAppSecret == null || wechatAppSecret.isBlank()) {
            throw new BizException(5000, "微信登录配置未完成");
        }

        Map<String, Object> response;
        try {
            String responseBody = wechatClient.get()
                    .uri(uriBuilder -> uriBuilder
                            .path("/sns/jscode2session")
                            .queryParam("appid", wechatAppId)
                            .queryParam("secret", wechatAppSecret)
                            .queryParam("js_code", req.code())
                            .queryParam("grant_type", "authorization_code")
                            .build())
                    .retrieve()
                    .body(String.class);
            response = objectMapper.readValue(responseBody, new TypeReference<Map<String, Object>>() {});
        } catch (Exception e) {
            log.error("调用微信 code2session 失败：{}", e.getMessage(), e);
            throw new BizException(5000, "微信登录服务暂时不可用");
        }

        String openid = response == null ? null : (String) response.get("openid");
        if (openid == null || openid.isBlank()) {
            String err = response == null ? "未知错误" : String.valueOf(response.getOrDefault("errmsg", "code无效"));
            throw new BizException(4010, "微信登录失败：" + err);
        }

        User user = userMapper.findByOpenid(openid).orElseGet(() -> {
            User u = new User();
            u.setOpenid(openid);
            u.setNickname(req.nickname() == null || req.nickname().isBlank() ? "微信用户" : req.nickname());
            u.setPasswordHash(PasswordUtil.hash("wechat-" + openid));
            u.setFamilyId(0L);
            u.setRole("owner");
            u.setCreatedAt(LocalDateTime.now());
            return userMapper.save(u);
        });
        return Result.ok(loginData(user));
    }

    /** 组装前端统一使用的 token、用户、家庭角色及头像信息。 */
    private Map<String, Object> loginData(User user) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("token", jwtUtil.createToken(user.getId()));
        Map<String, Object> info = new LinkedHashMap<>();
        info.put("id", user.getId());
        info.put("nickname", user.getNickname());
        info.put("familyId", user.getFamilyId());
        info.put("role", user.getRole());
        userProfileMapper.findById(user.getId()).ifPresent(profile -> info.put("avatarUrl", profile.getAvatarUrl()));
        data.put("user", info);
        return data;
    }
}
