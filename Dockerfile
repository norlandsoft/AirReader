FROM air-jdk:21

WORKDIR /app

RUN groupadd --system appuser && useradd --system --gid appuser appuser

COPY target/air-reader-2.0.0.jar ./app.jar

RUN mkdir -p /data && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://localhost:8000/api/v1/health || exit 1

ENTRYPOINT ["sh", "-c", "exec java ${JAVA_OPTS:--XX:MaxRAMPercentage=80.0 -XX:+UseSerialGC} -jar app.jar"]
