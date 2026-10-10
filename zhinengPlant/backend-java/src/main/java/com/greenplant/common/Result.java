package com.greenplant.common;

import lombok.Data;

/**
 * 统一响应体：{code, msg, data}，code=0 成功
 * 错误码约定（对齐接口文档）：
 * 4001 参数错误 / 4010 未登录 / 4030 无权限 / 4040 资源不存在 / 5000 服务器异常 / 6001 置信度过低
 */
@Data
public class Result<T> {

    private int code;
    private String msg;
    private T data;

    public static <T> Result<T> ok(T data) {
        Result<T> r = new Result<>();
        r.code = 0;
        r.msg = "ok";
        r.data = data;
        return r;
    }

    public static <T> Result<T> ok(String msg, T data) {
        Result<T> r = new Result<>();
        r.code = 0;
        r.msg = msg;
        r.data = data;
        return r;
    }

    public static <T> Result<T> error(int code, String msg) {
        Result<T> r = new Result<>();
        r.code = code;
        r.msg = msg;
        r.data = null;
        return r;
    }
}
