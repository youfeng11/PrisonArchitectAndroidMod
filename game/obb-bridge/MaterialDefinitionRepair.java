package com.paradoxplaza.prisonarchitect.patools;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Repairs repeated, identical Sprite declarations before the native parser reads them. */
final class MaterialDefinitionRepair {
    private MaterialDefinitionRepair() {}

    static byte[] repairNestedSprites(byte[] source) {
        String text = new String(source, StandardCharsets.ISO_8859_1);
        List<String> lines = new ArrayList<>();
        int start = 0;
        for (int i = 0; i < text.length(); ++i) {
            if (text.charAt(i) == '\n') {
                lines.add(text.substring(start, i + 1));
                start = i + 1;
            }
        }
        if (start < text.length()) lines.add(text.substring(start));
        String newline = text.contains("\r\n") ? "\r\n" : "\n";
        List<String> output = new ArrayList<>(lines.size());
        boolean repaired = false;
        for (int i = 0; i < lines.size(); ) {
            String kind = blockKind(lines.get(i));
            if (!"Sprite".equals(kind) && !"ToolbarSprite".equals(kind)) {
                output.add(lines.get(i++));
                continue;
            }
            int cursor = i + 1;
            List<String> body = new ArrayList<>();
            while (cursor < lines.size() && !isBoundary(lines.get(cursor))) body.add(lines.get(cursor++));
            Map<String, String> values = spriteFields(body);
            if (values == null) {
                output.add(lines.get(i++));
                continue;
            }
            List<String> extras = new ArrayList<>();
            boolean merged = false;
            while (cursor < lines.size() && kind.equals(blockKind(lines.get(cursor)))) {
                merged = true;
                ++cursor;
                List<String> duplicate = new ArrayList<>();
                while (cursor < lines.size() && !isBoundary(lines.get(cursor))) duplicate.add(lines.get(cursor++));
                Map<String, String> more = spriteFields(duplicate);
                if (more == null) return null;
                for (Map.Entry<String, String> entry : more.entrySet()) {
                    String value = values.get(entry.getKey());
                    if (value == null) {
                        values.put(entry.getKey(), entry.getValue());
                        extras.add(entry.getValue());
                    } else if (!value.equals(entry.getValue())) {
                        // Different rectangles describe distinct sprites; leave the file alone.
                        return null;
                    }
                }
            }
            if (!merged) {
                output.add(lines.get(i++));
                continue;
            }
            // The malformed run leaves its single END to close the enclosing object.
            output.add(lines.get(i));
            output.addAll(body);
            output.addAll(extras);
            output.add("END" + newline);
            i = cursor;
            repaired = true;
        }
        if (!repaired) return null;
        String contents = String.join("", output);
        return balanced(contents) ? contents.getBytes(StandardCharsets.ISO_8859_1) : null;
    }

    private static String blockKind(String line) {
        String[] tokens = line.trim().split("\\s+");
        return tokens.length == 2 && tokens[0].equals("BEGIN") ? tokens[1] : null;
    }

    private static boolean isBoundary(String line) {
        String trimmed = line.trim();
        return trimmed.equals("END") || trimmed.startsWith("BEGIN ") || trimmed.startsWith("BEGIN\t");
    }

    /* Map every "key value" line of one sprite block, rejecting repeated keys. */
    private static Map<String, String> spriteFields(List<String> lines) {
        Map<String, String> fields = new LinkedHashMap<>();
        for (String line : lines) {
            String trimmed = line.trim();
            if (trimmed.isEmpty()) continue;
            String[] tokens = trimmed.split("\\s+");
            if (tokens.length < 2 || fields.putIfAbsent(tokens[0], line) != null) return null;
        }
        return fields;
    }

    private static boolean balanced(String text) {
        int depth = 0;
        for (String token : text.split("\\s+")) {
            if (token.equals("BEGIN")) {
                ++depth;
            } else if (token.equals("END")) {
                if (--depth < 0) return false;
            }
        }
        return depth == 0;
    }
}
