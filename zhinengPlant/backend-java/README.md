# 绿植智能养护系统 · 后端（Java · Spring Boot + MySQL）

> 与同级 `zhinengPlant` 目录中的前端小程序配套，接口对齐 `docs/API接口文档.md`。
> 需求文档指定 MySQL 数据库（12 张表），本工程直接使用 MySQL 8。

## 技术栈

- Spring Boot 3.2.5（JDK 17）
- MyBatis 3（Mapper 接口 + XML 手写 SQL，表结构由 `schema.sql` 管理）
- MySQL 8（`mysql-connector-j`）
- JWT 认证（jjwt 0.12，Bearer Token）
- Maven 构建

## 三层架构

后端采用经典的 `Controller → Service → Mapper` 分层：

- `Controller`：接收 HTTP 参数、执行参数校验并返回统一 `Result`，不直接访问数据库。
- `Service`：承载登录、植物养护、家庭协作、知识库、诊断和导出等业务规则。
- `Mapper`：基于 MyBatis 接口和 XML SQL 完成实体与 MySQL 之间的数据访问。

调用链：`微信小程序 → Controller → Service → Mapper → MySQL`。AI 业务由 Service 通过 `AiGatewayService` 调用本地推理服务。

## 目录结构

```
backend-java/
├── pom.xml
└── src/main/
    ├── java/com/greenplant/
    │   ├── GreenplantApplication.java   # 启动类
    │   ├── common/                      # Result 统一响应 / JwtUtil / 拦截器 / 异常处理
    │   ├── config/                      # WebConfig（鉴权拦截 + CORS + 静态资源）
    │   ├── entity/                      # 12 张表实体
    │   ├── mapper/                      # MyBatis Mapper 接口
    │   ├── service/                     # 业务逻辑层
    │   ├── dto/                         # 请求体（record）
    │   ├── ai/                          # MockAiService（识别/诊断占位推理）
    │   └── controller/                  # HTTP 接口层，只调用 Service
    └── resources/
        ├── mapper/                      # MyBatis XML；SELECT/INSERT/UPDATE/DELETE SQL
        ├── application.yml              # 端口 8081、环境变量导入、JWT/AI 配置
        ├── schema.sql                   # 12 张表 MySQL DDL（启动重建）
        └── data.sql                     # 6 品种知识库 + 测试账号
```

## 启动步骤

1. **启动 MySQL**：系统设置 → MySQL → Start，或 `sudo /usr/local/mysql/support-files/mysql.server start`
2. **填写配置**：编辑项目总目录 `/Users/ccx/Plant/.env` 中的 MySQL、微信等配置
3. **运行**（二选一）：
   - IDEA：File → Open 选 `backend-java` → 等 Maven 依赖下载 → 运行 `GreenplantApplication`
   - 命令行：`mvn spring-boot:run`

启动后浏览器打开 **http://127.0.0.1:8081/api/health** 看到 `{"code":0,...}` 即成功。

## 接口调试

Spring Boot 已内置 **Swagger UI**（springdoc 依赖可选，未引入）。当前可直接用浏览器/curl 调试：

```bash
curl http://127.0.0.1:8081/api/health
curl -X POST http://127.0.0.1:8081/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"phone":"13800000000","password":"123456","nickname":"绿植主人"}'
```

注册返回 `token` 后，请求带 `Authorization: Bearer <token>`。

> 若需要 Swagger 页面（/swagger-ui.html），在 pom.xml 加 `springdoc-openapi-starter-webmvc-ui` 即可。

## 统一响应与错误码

```json
{ "code": 0, "msg": "ok", "data": { } }
```

- 0 成功；4001 参数错误；4010 未登录；4030 无权限；4040 资源不存在；5000 服务器异常；6001 置信度过低

## 前端对接（切换真实后端）

1. `utils/request.js`：`MOCK = false`
2. `app.js`：模拟器使用 `http://127.0.0.1:8081/api`；真机使用电脑局域网 IP，例如 `http://192.168.1.100:8081/api`
3. 微信开发者工具 → 详情 → 本地设置 → 勾选「不校验合法域名」

## 待办（接真实能力）

- [ ] 品种识别 / 健康诊断：Colab 训练模型 → 替换 `MockAiService.recognize()/diagnose()`
- [ ] 微信登录 code2session（需正式 AppID + Secret，测试号无法验证）
- [ ] 导出真实文件：Apache POI（Excel）/ OpenPDF（PDF），生成后返回 `/uploads/...` URL
- [ ] 图片上传存 OSS/MinIO（当前仅 mock 推理不落盘）
- [ ] JWT 密钥改为环境变量注入、密码哈希换 BCrypt（课设可保持现状）
