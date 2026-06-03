package com.airfilereader.service;

import java.io.*;
import java.nio.file.*;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;

/** Calls opendataloader-pdf-cli.jar via ProcessBuilder for PDF extraction. */
public class OpenDataLoaderService {

    private static final String JAR_PATH;
    private static final String JAVA_HOME;

    static {
        String jarFromProp = System.getProperty("odl.jar.path");
        if (jarFromProp != null && Files.exists(Path.of(jarFromProp))) {
            JAR_PATH = jarFromProp;
        } else {
            String[] candidates = {"lib/opendataloader-pdf-cli.jar", "/app/lib/opendataloader-pdf-cli.jar"};
            String found = null;
            for (String c : candidates) {
                if (Files.exists(Path.of(c))) { found = c; break; }
            }
            JAR_PATH = found != null ? found : "lib/opendataloader-pdf-cli.jar";
        }

        String jh = System.getenv("JAVA_HOME");
        JAVA_HOME = (jh != null && !jh.isBlank()) ? jh : System.getProperty("java.home");
    }

    public record ExtractionResult(String markdown, int pageCount, long fileSizeBytes) {}

    public ExtractionResult extract(Path pdfPath, String originalFilename) throws Exception {
        if (!Files.exists(pdfPath)) {
            throw new FileNotFoundException("File not found: " + pdfPath);
        }

        long fileSize = Files.size(pdfPath);
        Path tempDir = Files.createTempDirectory("odl_");

        try {
            String javaBin = Path.of(JAVA_HOME, "bin", "java").toString();
            List<String> cmd = new ArrayList<>(List.of(
                javaBin, "-jar", JAR_PATH,
                "--input", pdfPath.toAbsolutePath().toString(),
                "--output-dir", tempDir.toAbsolutePath().toString(),
                "--format", "markdown",
                "--quiet"
            ));

            Process process = new ProcessBuilder(cmd).redirectErrorStream(true).start();
            boolean finished = process.waitFor(300, TimeUnit.SECONDS);

            if (!finished) {
                process.destroyForcibly();
                throw new IOException("OpenDataLoader conversion timed out (300s)");
            }

            String procOutput = new String(process.getInputStream().readAllBytes());
            if (process.exitValue() != 0) {
                throw new IOException("OpenDataLoader exited " + process.exitValue() + ": " + procOutput);
            }

            // Find .md output
            String stem = stripExtension(originalFilename != null ? Path.of(originalFilename).getFileName().toString() : pdfPath.getFileName().toString());
            Path mdFile = tempDir.resolve(stem + ".md");
            if (!Files.exists(mdFile)) {
                try (Stream<Path> s = Files.list(tempDir)) {
                    mdFile = s.filter(p -> p.toString().endsWith(".md")).findFirst().orElse(null);
                }
            }
            if (mdFile == null) {
                throw new IOException("OpenDataLoader produced no markdown output. Files: " + Files.list(tempDir).toList());
            }

            String markdown = Files.readString(mdFile);
            return new ExtractionResult(markdown, 0, fileSize);

        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IOException("Conversion interrupted", e);
        } finally {
            try (Stream<Path> s = Files.walk(tempDir)) {
                s.sorted(Comparator.reverseOrder()).forEach(p -> {
                    try { Files.deleteIfExists(p); } catch (IOException ignored) {}
                });
            } catch (IOException ignored) {}
        }
    }

    private static String stripExtension(String filename) {
        int dot = filename.lastIndexOf('.');
        return dot > 0 ? filename.substring(0, dot) : filename;
    }
}
