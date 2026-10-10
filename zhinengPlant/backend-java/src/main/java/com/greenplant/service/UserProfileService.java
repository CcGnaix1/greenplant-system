package com.greenplant.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import com.greenplant.common.BizException;
import com.greenplant.common.Result;
import com.greenplant.common.UserContext;
import com.greenplant.entity.UserProfile;
import com.greenplant.mapper.UserProfileMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.multipart.MultipartFile;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

@Service
@RequiredArgsConstructor
/** 用户资料业务：校验并保存用户自定义头像。 */
public class UserProfileService {
    private static final Set<String> ALLOWED = Set.of("image/jpeg", "image/png", "image/webp");
    private final UserProfileMapper profileMapper;

    @Value("${app.upload-dir:./uploads}")
    private String uploadDir;

    /** 接收 JPG/PNG/WebP 头像，限制 5MB，保存文件并更新头像地址。 */
    @Transactional
    public Result<Map<String, String>> uploadAvatar(MultipartFile avatar) {
        if (avatar == null || avatar.isEmpty()) throw new BizException(4000, "请选择头像图片");
        if (!ALLOWED.contains(avatar.getContentType())) throw new BizException(4000, "头像仅支持 JPG、PNG 或 WebP 格式");
        if (avatar.getSize() > 5 * 1024 * 1024L) throw new BizException(4000, "头像不能超过 5MB");
        try {
            String ext = switch (avatar.getContentType()) {
                case "image/png" -> ".png";
                case "image/webp" -> ".webp";
                default -> ".jpg";
            };
            Path dir = Paths.get(uploadDir).toAbsolutePath().normalize().resolve("avatars");
            Files.createDirectories(dir);
            String fileName = UserContext.get() + "-" + UUID.randomUUID() + ext;
            Files.copy(avatar.getInputStream(), dir.resolve(fileName), StandardCopyOption.REPLACE_EXISTING);
            String url = "/uploads/avatars/" + fileName;
            UserProfile profile = profileMapper.findById(UserContext.get()).orElseGet(UserProfile::new);
            profile.setUserId(UserContext.get());
            profile.setAvatarUrl(url);
            profileMapper.save(profile);
            return Result.ok(Map.of("avatarUrl", url));
        } catch (Exception e) {
            throw new BizException(5000, "头像保存失败，请稍后重试");
        }
    }
}
