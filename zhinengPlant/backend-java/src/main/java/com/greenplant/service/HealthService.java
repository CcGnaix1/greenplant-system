package com.greenplant.service;

import com.greenplant.common.Result;
import org.springframework.stereotype.Service;
import java.util.Map;

@Service
/** 服务健康检查，用于确认 Java 后端和数据库配置已成功加载。 */
public class HealthService {
    /** 返回当前后端运行状态与主要技术栈。 */

    public Result<Map<String, Object>> health() {
        return Result.ok(Map.of("status", "running", "stack", "Spring Boot + MySQL"));
    }
}
