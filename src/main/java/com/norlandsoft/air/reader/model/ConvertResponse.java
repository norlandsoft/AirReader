package com.norlandsoft.air.reader.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

import java.util.ArrayList;
import java.util.List;

/**
 * 错误响应体（仅用于 HTTP 错误场景）
 *
 * 成功响应直接返回 application/zip 流，不经过此模型。
 *
 * @author ChaiMingXu
 * @since 2026-06-03
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class ConvertResponse {

    private String status;
    private double processingTime;
    private List<ConvertError> errors;

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public double getProcessingTime() { return processingTime; }
    public void setProcessingTime(double processingTime) { this.processingTime = processingTime; }

    public List<ConvertError> getErrors() { return errors; }
    public void setErrors(List<ConvertError> errors) { this.errors = errors; }

    /**
     * 构建失败响应
     */
    public static ConvertResponse failure(String errorCode, String message, double processingTimeSec) {
        ConvertResponse resp = new ConvertResponse();
        resp.setStatus("failure");
        resp.setProcessingTime(processingTimeSec);
        List<ConvertError> errors = new ArrayList<>();
        errors.add(new ConvertError(errorCode, message));
        resp.setErrors(errors);
        return resp;
    }

    /**
     * 转换错误
     */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class ConvertError {

        private String code;
        private String message;

        public ConvertError() {}

        public ConvertError(String code, String message) {
            this.code = code;
            this.message = message;
        }

        public String getCode() { return code; }
        public void setCode(String code) { this.code = code; }

        public String getMessage() { return message; }
        public void setMessage(String message) { this.message = message; }
    }
}
