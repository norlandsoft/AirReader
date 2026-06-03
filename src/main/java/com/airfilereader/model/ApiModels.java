package com.airfilereader.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** Unified API response models matching the docling-style envelope. */
public class ApiModels {

    public enum ErrorCode {
        INVALID_REQUEST,
        UNSUPPORTED_FORMAT,
        EMPTY_FILE,
        FILE_TOO_LARGE,
        EXTRACTION_FAILED,
        NOT_FOUND,
        INTERNAL_ERROR
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record ApiError(ErrorCode code, String message, String detail) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record DocumentInfo(
            String filename,
            String format,
            String type,
            int page_count,
            long file_size_bytes) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record ContentInfo(String format, String text, int length) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record ExtractionData(DocumentInfo document, ContentInfo content) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record ResponseMetadata(
            String request_id,
            String timestamp,
            String api_version,
            double processing_time_ms) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record ApiResponse(
            String status,
            Object data,
            List<ApiError> errors,
            ResponseMetadata metadata) {

        public static ApiResponse success(Object data, String requestId, double processingTimeMs) {
            return new ApiResponse("success", data, List.of(),
                    new ResponseMetadata(
                            requestId != null ? requestId : UUID.randomUUID().toString().replace("-", ""),
                            Instant.now().toString(),
                            "1.0.0",
                            Math.round(processingTimeMs * 100.0) / 100.0));
        }

        public static ApiResponse error(List<ApiError> errors, String requestId) {
            return new ApiResponse("error", null, errors,
                    new ResponseMetadata(
                            requestId != null ? requestId : UUID.randomUUID().toString().replace("-", ""),
                            Instant.now().toString(),
                            "1.0.0",
                            0.0));
        }
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record HealthData(String service, String version, String status) {
        public static HealthData ok() {
            return new HealthData("AirFileReader", "1.0.0", "healthy");
        }
    }
}
