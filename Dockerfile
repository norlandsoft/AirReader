FROM eclipse-temurin:21-jdk-alpine

WORKDIR /app

RUN addgroup -S appuser && adduser -S appuser -G appuser

COPY target/air-reader-2.0.0.jar ./app.jar

RUN mkdir -p /data && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://localhost:8000/api/v1/health || exit 1

CMD ["java", "-jar", "app.jar"]
