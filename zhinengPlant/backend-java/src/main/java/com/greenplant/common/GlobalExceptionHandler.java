package com.greenplant.common;

import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

/** 全局异常 → 统一响应 {code,msg,data} */
@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(BizException.class)
    public Result<Void> biz(BizException e) {
        return Result.error(e.getCode(), e.getMessage());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public Result<Void> valid(MethodArgumentNotValidException e) {
        String msg = e.getBindingResult().getFieldErrors().stream()
                .map(f -> f.getField() + " " + f.getDefaultMessage())
                .findFirst().orElse("参数错误");
        return Result.error(4001, msg);
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public Result<Void> upload(MaxUploadSizeExceededException e) {
        return Result.error(4001, "图片大小超过限制（10MB）");
    }

    @ExceptionHandler(Exception.class)
    public Result<Void> other(Exception e) {
        log.error("服务器异常", e);
        return Result.error(5000, "服务器异常：" + e.getMessage());
    }
}
