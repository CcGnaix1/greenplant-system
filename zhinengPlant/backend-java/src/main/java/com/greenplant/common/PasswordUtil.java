package com.greenplant.common;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/** 密码哈希：SHA-256 hex（课设演示用；生产可换 BCrypt） */
public final class PasswordUtil {

    private PasswordUtil() {
    }

    public static String hash(String raw) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] d = md.digest(raw.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : d) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (Exception e) {
            throw new IllegalStateException("密码哈希失败", e);
        }
    }
}
