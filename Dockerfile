# ---- Build stage: compile with Maven ----
FROM maven:3.9-eclipse-temurin-21 AS builder

WORKDIR /build

COPY pom.xml .
COPY lib/ lib/
RUN mvn dependency:go-offline -q

COPY src/ src/
RUN mvn clean package -DskipTests -q

# ---- Runtime stage: JDK only ----
FROM eclipse-temurin:21-jdk-alpine

WORKDIR /app

RUN addgroup -S appuser && adduser -S appuser -G appuser

COPY --from=builder /build/target/air-filereader-1.0.0.jar ./app.jar

# Copy the ODL JAR for ProcessBuilder
COPY lib/opendataloader-pdf-cli.jar ./lib/

RUN mkdir -p /data && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://localhost:8000/api/v1/health || exit 1

CMD ["java", "-jar", "app.jar"]
