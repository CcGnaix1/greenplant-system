# 绿植智能养护系统・后端接口文档（v1）

> 依据《基于图像识别的绿植智能养护系统》需求方案 第六章「接口设计」整理，供后端（Python FastAPI + MySQL）实现与前端小程序联调使用。
> 前端工程：
>
> 小程序目录：`Plant/zhinengPlant`
>
> （微信小程序原生）。当前前端以 
>
> `utils/mock.js`
>
>  驱动，后端就绪后按本文档对接。



***

## 1. 通用约定



| 项        | 约定                                                       |
| -------- | -------------------------------------------------------- |
| Base URL | `http://<host>:<port>/api`                               |
| 数据格式     | JSON（文件上传除外，走 `multipart/form-data`）                     |
| 认证       | 除登录 / 注册外，所有请求头携带 `Authorization: Bearer <JWT>`          |
| 统一响应体    | `{ "code": 0, "msg": "ok", "data": {...} }`，`code=0` 为成功 |
| 分页参数     | `page`（从 1 开始）、`size`                                    |
| 时间格式     | `yyyy-MM-dd HH:mm:ss`                                    |
| 传输安全     | 全部 HTTPS；养护照片存私有对象存储，访问走服务端签名 URL                        |

### 1.1 错误码



| code | 含义            | 前端处理                   |
| ---- | ------------- | ---------------------- |
| 0    | 成功            | 取 `data`               |
| 4001 | 参数错误          | toast 提示               |
| 4010 | 未登录 /token 过期 | 清登录态，跳登录页              |
| 4030 | 无权限（非该家庭成员）   | toast 无权限              |
| 4040 | 资源不存在         | toast 或回退              |
| 5000 | 服务器异常         | toast，重试               |
| 6001 | 识别置信度过低       | 提示 "无法确认"，允许手动选品种 / 反馈 |



***

## 2. 接口总表

### 2.1 用户与家庭



| 方法    | 路径                               | 说明                                   |
| ----- | -------------------------------- | ------------------------------------ |
| POST  | `/auth/register`                 | 注册 `{phone, password, nickname}`     |
| POST  | `/auth/login`                    | 登录，返回 token 与用户信息                    |
| POST  | `/auth/wechat`                   | **【小程序补充】** 用 `code` 换 openid，下发 JWT |
| POST  | `/family`                        | 创建家庭组                                |
| POST  | `/family/{id}/invite`            | 生成邀请码 / 链接                           |
| POST  | `/family/{id}/members`           | 添加成员 `{userId, role}`                |
| GET   | `/family/{id}/members`           | 成员列表                                 |
| POST  | `/family/{id}/tasks`             | 分配养护任务                               |
| GET   | `/family/{id}/tasks?status=todo` | 任务列表                                 |
| PATCH | `/tasks/{taskId}/done`           | 完成 / 取消任务                            |

### 2.2 植物档案



| 方法     | 路径                                       | 说明                         |
| ------ | ---------------------------------------- | -------------------------- |
| POST   | `/plants`                                | 建档（识别来源带 `speciesId` 自动回填） |
| GET    | `/plants?familyId=&keyword=&page=&size=` | 我的 / 家庭植物列表                |
| GET    | `/plants/{id}`                           | 档案详情（含环境偏好、最近养护）           |
| PATCH  | `/plants/{id}`                           | 编辑档案                       |
| POST   | `/plants/{id}/photo`                     | 上传封面照（multipart）           |
| DELETE | `/plants/{id}`                           | 归档 / 删除                    |

### 2.3 养护记录与可视化



| 方法   | 路径                          | 说明                                       |
| ---- | --------------------------- | ---------------------------------------- |
| POST | `/plants/{id}/care-records` | 添加养护记录（浇水 / 施肥 / 修剪 / 换盆 / 松土 / 喷药 / 擦叶） |
| POST | `/plants/{id}/watering`     | 一键浇水（`opTime` 默认当前时间）                    |
| GET  | `/plants/{id}/timeline`     | 时光轴（事件 + 状态照，时间倒序）                       |
| GET  | `/plants/{id}/stats`        | 浇水频率折线、高度变化数据                            |
| POST | `/plants/{id}/growth`       | 记录一次生长测量                                 |

### 2.4 智能识别与诊断



| 方法   | 路径                         | 说明                                        |
| ---- | -------------------------- | ----------------------------------------- |
| POST | `/species/recognize`       | 品种识别（multipart 图片字段 `image`，云端兜底）         |
| POST | `/diagnosis`               | 上传照片做健康诊断（multipart `image`，可选 `plantId`） |
| GET  | `/diagnosis/{id}`          | 诊断详情                                      |
| POST | `/diagnosis/{id}/feedback` | 用户纠错反馈（回流再训练）                             |

### 2.5 知识库与个性化提醒



| 方法    | 路径                               | 说明                                           |
| ----- | -------------------------------- | -------------------------------------------- |
| GET   | `/knowledge/species/{speciesId}` | 品种知识首页（习性 / 四季日历 / 浇水 / 施肥 / 繁殖 / FAQ / 视频位） |
| GET   | `/knowledge/search?keyword=`     | 知识搜索                                         |
| GET   | `/plants/{id}/care-plan`         | 个性化养护计划（含下次日期与动态文案要素）                        |
| GET   | `/notifications?isRead=0`        | 未读提醒列表                                       |
| PATCH | `/notifications/{id}/read`       | 标记已读                                         |

### 2.6 数据导出



| 方法  | 路径                                          | 说明                        |
| --- | ------------------------------------------- | ------------------------- |
| GET | `/export/plant/{plantId}?format=pdf\|excel` | 导出单株档案 + 养护记录（返回文件下载 URL） |
| GET | `/export/records?format=excel&start=&end=`  | 按时间导出养护记录                 |



***

## 3. 关键接口示例

### 3.1 微信登录（小程序补充，需后端实现）

小程序端调用 `wx.login()` 拿到 `code`，发到后端；后端用 `appid + secret + code` 调微信 `code2session` 换 `openid`，签发本系统 JWT。



```
POST /api/auth/wechat

{ "code": "wx\_login\_code" }
```



```
{

&#x20; "code": 0,

&#x20; "data": {

&#x20;   "token": "eyJhbGciOi...",

&#x20;   "user": { "id": 1, "nickname": "绿植主人", "familyId": 1, "role": "owner" },

&#x20;   "isNew": false

&#x20; }

}
```

### 3.2 快速建档



```
POST /api/plants

{

&#x20; "name": "阳台绿萝",

&#x20; "speciesId": 1001,

&#x20; "purchaseDate": "2026-09-01",

&#x20; "potMaterial": "陶瓷",

&#x20; "initHeightCm": 12.0,

&#x20; "emotionTag": "生日礼物",

&#x20; "photoUrl": null

}
```

携带 `speciesId` 时，后端自动附品种环境偏好快照（温度、湿度、光照、浇水间隔），前端仅需 "补充或确认"。

### 3.3 一键浇水



```
POST /api/plants/88/watering

{ "note": "周末例行" }
```



```
{

&#x20; "code": 0,

&#x20; "data": { "careRecordId": 552, "opTime": "2026-09-07 09:30:00", "nextDueDate": "2026-09-11" }

}
```

### 3.4 品种识别



```
POST /api/species/recognize        (multipart: image=@leaf.jpg)
```



```
{

&#x20; "code": 0,

&#x20; "data": {

&#x20;   "candidates": \[

&#x20;     { "speciesId": 1001, "species": "绿萝", "confidence": 0.94, "desc": "天南星科，喜温暖湿润" },

&#x20;     { "speciesId": 1002, "species": "龟背竹", "confidence": 0.41 }

&#x20;   ]

&#x20; }

}
```

`confidence < 阈值` 时后端返回 `code=6001`，前端提示手动选择。

### 3.5 健康诊断（拍照）



```
POST /api/diagnosis                (multipart: image=@leaf.jpg, 可选 plantId=88)
```



```
{

&#x20; "code": 0,

&#x20; "data": {

&#x20;   "diagnosisId": 21,

&#x20;   "symptoms": \[

&#x20;     { "code": "yellowing\_edge", "label": "叶缘黄化", "prob": 0.91, "active": true },

&#x20;     { "code": "overwater", "label": "水多", "prob": 0.78, "active": true }

&#x20;   ],

&#x20;   "report": {

&#x20;     "suspectProblem": "疑似浇水过多导致的叶缘黄化",

&#x20;     "causeAnalysis": "土壤长期潮湿、排水不畅，根系缺氧……",

&#x20;     "emergencySteps": "1.立即停水并松土通风 2.检查盆底积水 3.剪除严重黄叶",

&#x20;     "longTermAdvice": "调整至见干见湿，雨季降低频次……"

&#x20;   }

&#x20; }

}
```

### 3.6 个性化养护计划



```
GET /api/plants/88/care-plan
```



```
{

&#x20; "code": 0,

&#x20; "data": \[

&#x20;   {

&#x20;     "taskType": "watering",

&#x20;     "plantName": "阳台绿萝",

&#x20;     "habit": "喜湿润",

&#x20;     "dryDays": 5,

&#x20;     "suggestion": "建议在傍晚浇透水",

&#x20;     "lastDoneAt": "2026-09-02 18:20:00",

&#x20;     "nextDueDate": "2026-09-09"

&#x20;   }

&#x20; ]

}
```



***

## 4. 小程序对接说明



| 场景           | 小程序 API                                                   | 后端配合                                           |
| ------------ | --------------------------------------------------------- | ---------------------------------------------- |
| 普通请求         | `wx.request`                                              | 走上表 REST 接口                                    |
| 拍照 / 相册上传    | `wx.chooseMedia` + `wx.uploadFile`（`formData: {plantId}`） | `/species/recognize`、`/diagnosis` 接收 multipart |
| 登录           | `wx.login` 取 code → `/auth/wechat`                        | code2session 换 openid                          |
| 导出 PDF/Excel | `wx.downloadFile` 下载 → `wx.openDocument`                  | 返回可下载文件 URL                                    |
| 真机调试         | 开发者工具勾选 "不校验合法域名"                                         | 上线前配置 HTTPS 域名                                 |

## 5. 前端 mock 与真实接口对照

当前前端 `utils/request.js` 为 MOCK 模式，路由与上表对应：



| 前端 mock 调用                              | 对应真实接口                                                  |
| --------------------------------------- | ------------------------------------------------------- |
| `/plant/list`                           | `GET /plants`                                           |
| `/plant/detail`                         | `GET /plants/{id}`                                      |
| `/plant/records`                        | `GET /plants/{id}/timeline`                             |
| `/species/recognize`                    | `POST /species/recognize`                               |
| `/diagnose/submit`                      | `POST /diagnosis`                                       |
| `/knowledge/list` / `/knowledge/detail` | `GET /knowledge/search` / `GET /knowledge/species/{id}` |
| `/family/info`                          | `GET /family/{id}/members` + `GET /family/{id}/tasks`   |
| `/notification/list`                    | `GET /notifications?isRead=0`                           |

后端就绪后：前端 `utils/request.js` 顶部 `MOCK = false`，并在 `app.js` 填入真实 `baseUrl` 即可全量切换。
