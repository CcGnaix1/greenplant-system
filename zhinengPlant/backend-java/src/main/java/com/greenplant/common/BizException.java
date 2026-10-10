package com.greenplant.common;

/** 业务异常：携带错误码，由全局异常处理器转为统一响应 */
public class BizException extends RuntimeException {

    private final int code;

    public BizException(int code, String msg) {
        super(msg);
        this.code = code;
    }

    public int getCode() {
        return code;
    }
}
