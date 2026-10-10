package com.greenplant.service;

import com.lowagie.text.Document;
import com.lowagie.text.Element;
import com.lowagie.text.Font;
import com.lowagie.text.PageSize;
import com.lowagie.text.Paragraph;
import com.lowagie.text.pdf.BaseFont;
import com.lowagie.text.pdf.PdfPCell;
import com.lowagie.text.pdf.PdfPTable;
import com.lowagie.text.pdf.PdfWriter;
import com.greenplant.common.BizException;
import com.greenplant.common.Result;
import com.greenplant.common.UserContext;
import com.greenplant.entity.CareRecord;
import com.greenplant.entity.PlantProfile;
import com.greenplant.mapper.CareRecordMapper;
import com.greenplant.mapper.PlantProfileMapper;
import com.greenplant.mapper.UserMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.BorderStyle;
import org.apache.poi.ss.usermodel.CellStyle;
import org.apache.poi.ss.usermodel.FillPatternType;
import org.apache.poi.ss.usermodel.HorizontalAlignment;
import org.apache.poi.ss.usermodel.IndexedColors;
import org.apache.poi.ss.usermodel.VerticalAlignment;
import org.apache.poi.ss.util.CellRangeAddress;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 数据导出（PDF/Excel），文件生成到 uploads/exports 并通过静态资源地址下载。
 */
@Service
@RequiredArgsConstructor
@Slf4j
/** 导出业务：把养护记录整理为中文明细，并生成 PDF 或 Excel 文件。 */
public class ExportService {

    private static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final DateTimeFormatter FMT_CN = DateTimeFormatter.ofPattern("yyyy年MM月dd日 HH:mm:ss");

    private final PlantProfileMapper plantMapper;
    private final CareRecordMapper recordMapper;
    private final UserMapper userMapper;

    @Value("${app.upload-dir}")
    private String uploadDir;

    /** 导出单盆植物的档案信息和全部养护明细。 */
    public Result<Map<String, Object>> exportPlant(Long plantId,
                                                   String format) {
        PlantProfile p = plantMapper.findById(plantId)
                .orElseThrow(() -> new BizException(4040, "植物不存在"));
        if (!p.getUserId().equals(UserContext.get())) {
            throw new BizException(4030, "无权访问该植物");
        }
        List<CareRecord> records = recordMapper.findByPlantIdOrderByCreatedAtDesc(plantId);

        Map<String, Object> plant = new LinkedHashMap<>();
        plant.put("name", p.getName());
        plant.put("heightCm", p.getInitHeightCm());
        plant.put("potMaterial", p.getPotMaterial());
        plant.put("emotionTag", p.getEmotionTag());
        plant.put("createdAt", p.getCreatedAt() == null ? null : p.getCreatedAt().format(FMT));

        List<Map<String, Object>> rows = new ArrayList<>();
        for (int i = 0; i < records.size(); i++) {
            rows.add(toExportRow(records.get(i), i + 1, p.getName()));
        }

        String fileUrl = generateFile(format, "plant-" + plantId, p.getName() + "养护记录明细表", rows);
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("plant", plant);
        data.put("recordCount", rows.size());
        data.put("records", rows);
        data.put("fileUrl", fileUrl);
        return Result.ok(data);
    }

    /** 按起止日期导出当前用户全部植物的养护记录。 */
    public Result<Map<String, Object>> exportRecords(String format,
                                                     String start,
                                                     String end) {
        List<CareRecord> all = recordMapper.findByUserIdOrderByCreatedAtDesc(UserContext.get());
        LocalDateTime startTime = parseDate(start, false);
        LocalDateTime endTime = parseDate(end, true);
        Map<Long, String> plantNames = new HashMap<>();
        plantMapper.findByUserIdOrderByCreatedAtDesc(UserContext.get())
                .forEach(p -> plantNames.put(p.getId(), p.getName()));
        List<CareRecord> filtered = all.stream()
                .filter(r -> inRange(r.getCreatedAt(), startTime, endTime))
                .toList();
        List<Map<String, Object>> rows = new ArrayList<>();
        for (int i = 0; i < filtered.size(); i++) {
            CareRecord record = filtered.get(i);
            rows.add(toExportRow(record, i + 1,
                    plantNames.getOrDefault(record.getPlantId(), "未命名植物")));
        }
        String fileUrl = generateFile(format, "care-records", "绿植养护记录明细表", rows);
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("count", rows.size());
        data.put("rows", rows);
        data.put("fileUrl", fileUrl);
        return Result.ok(data);
    }

    private Map<String, Object> toExportRow(CareRecord record, int sequence, String plantName) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("sequence", sequence);
        row.put("plantName", plantName == null || plantName.isBlank() ? "未命名植物" : plantName);
        row.put("plantId", record.getPlantId());
        row.put("type", careTypeName(record.getType()));
        row.put("note", careDescription(record.getType(), record.getNote()));
        row.put("operator", userMapper.findById(record.getUserId())
                .map(u -> u.getNickname() == null || u.getNickname().isBlank() ? "本人" : u.getNickname())
                .orElse("本人"));
        row.put("time", record.getCreatedAt() == null ? "时间未知" : record.getCreatedAt().format(FMT_CN));
        return row;
    }

    private String careTypeName(String type) {
        if (type == null) {
            return "其他养护";
        }
        return switch (type.toLowerCase()) {
            case "water", "watering" -> "浇水";
            case "fertilize", "fertilization" -> "施肥";
            case "prune", "pruning" -> "修剪";
            case "repot" -> "换盆";
            case "rotate" -> "转盆";
            case "check" -> "状态检查";
            case "spray" -> "叶面喷雾";
            case "clean" -> "叶片清洁";
            case "sun", "lighting" -> "光照调整";
            default -> "其他养护";
        };
    }

    private String careDescription(String type, String note) {
        if (note != null && !note.isBlank()) {
            return note;
        }
        return switch (careTypeName(type)) {
            case "浇水" -> "已完成本次浇水养护";
            case "施肥" -> "已完成本次施肥养护";
            case "修剪" -> "已完成枝叶修剪";
            case "换盆" -> "已完成换盆及土壤整理";
            case "转盆" -> "已调整花盆朝向";
            case "状态检查" -> "已检查植物生长状态";
            case "叶面喷雾" -> "已完成叶面喷雾";
            case "叶片清洁" -> "已完成叶片清洁";
            case "光照调整" -> "已调整植物光照位置";
            default -> "已完成一次日常养护";
        };
    }

    private LocalDateTime parseDate(String value, boolean endOfDay) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            LocalDate date = LocalDate.parse(value);
            return endOfDay ? date.plusDays(1).atStartOfDay().minusNanos(1) : date.atStartOfDay();
        } catch (DateTimeParseException e) {
            throw new BizException(4000, "日期格式应为 yyyy-MM-dd");
        }
    }

    private boolean inRange(LocalDateTime time, LocalDateTime start, LocalDateTime end) {
        if (time == null) {
            return false;
        }
        return (start == null || !time.isBefore(start)) && (end == null || !time.isAfter(end));
    }

    /** 根据 format 选择生成器，将文件保存到 uploads/exports 并返回下载地址。 */
    private String generateFile(String format, String prefix, String title, List<Map<String, Object>> rows) {
        String normalized = "excel".equalsIgnoreCase(format) ? "excel" : "pdf";
        String ext = "excel".equals(normalized) ? "xlsx" : "pdf";
        String fileName = prefix + "-" + System.currentTimeMillis() + "." + ext;
        try {
            Path dir = Paths.get(uploadDir, "exports").toAbsolutePath().normalize();
            Files.createDirectories(dir);
            Path target = dir.resolve(fileName);
            if ("excel".equals(normalized)) {
                writeExcel(target, title, rows);
            } else {
                writePdf(target, title, rows);
            }
            return "/uploads/exports/" + fileName;
        } catch (Exception e) {
            log.error("导出文件生成失败", e);
            throw new BizException(5000, "导出文件生成失败");
        }
    }

    /** 使用 Apache POI 生成带中文表头、样式和列宽的 Excel。 */
    private void writeExcel(Path target, String title, List<Map<String, Object>> rows) throws Exception {
        try (XSSFWorkbook workbook = new XSSFWorkbook(); OutputStream out = Files.newOutputStream(target)) {
            Sheet sheet = workbook.createSheet("养护记录");
            CellStyle titleStyle = workbook.createCellStyle();
            org.apache.poi.ss.usermodel.Font excelTitleFont = workbook.createFont();
            excelTitleFont.setBold(true);
            excelTitleFont.setFontHeightInPoints((short) 16);
            titleStyle.setFont(excelTitleFont);
            titleStyle.setAlignment(HorizontalAlignment.CENTER);

            CellStyle headerStyle = workbook.createCellStyle();
            org.apache.poi.ss.usermodel.Font headerFont = workbook.createFont();
            headerFont.setBold(true);
            headerStyle.setFont(headerFont);
            headerStyle.setAlignment(HorizontalAlignment.CENTER);
            headerStyle.setVerticalAlignment(VerticalAlignment.CENTER);
            headerStyle.setFillForegroundColor(IndexedColors.LIGHT_GREEN.getIndex());
            headerStyle.setFillPattern(FillPatternType.SOLID_FOREGROUND);
            setBorders(headerStyle);

            CellStyle bodyStyle = workbook.createCellStyle();
            bodyStyle.setVerticalAlignment(VerticalAlignment.CENTER);
            bodyStyle.setWrapText(true);
            setBorders(bodyStyle);

            Row titleRow = sheet.createRow(0);
            titleRow.setHeightInPoints(28);
            titleRow.createCell(0).setCellValue(title);
            titleRow.getCell(0).setCellStyle(titleStyle);
            sheet.addMergedRegion(new CellRangeAddress(0, 0, 0, 6));

            Row summary = sheet.createRow(1);
            summary.createCell(0).setCellValue("导出时间：" + LocalDateTime.now().format(FMT_CN)
                    + "    记录总数：" + rows.size() + " 条");
            sheet.addMergedRegion(new CellRangeAddress(1, 1, 0, 6));

            Row header = sheet.createRow(2);
            String[] headers = {"序号", "植物名称", "植物编号", "养护项目", "养护说明", "操作人", "养护时间"};
            for (int i = 0; i < headers.length; i++) {
                header.createCell(i).setCellValue(headers[i]);
                header.getCell(i).setCellStyle(headerStyle);
            }
            int index = 3;
            for (Map<String, Object> item : rows) {
                Row row = sheet.createRow(index++);
                Object[] values = {item.get("sequence"), item.get("plantName"), item.get("plantId"),
                        item.get("type"), item.get("note"), item.get("operator"), item.get("time")};
                for (int i = 0; i < values.length; i++) {
                    row.createCell(i).setCellValue(value(values[i]));
                    row.getCell(i).setCellStyle(bodyStyle);
                }
            }
            int[] widths = {8, 18, 12, 16, 38, 16, 27};
            for (int i = 0; i < widths.length; i++) {
                sheet.setColumnWidth(i, widths[i] * 256);
            }
            sheet.createFreezePane(0, 3);
            sheet.setAutoFilter(new CellRangeAddress(2, Math.max(2, index - 1), 0, 6));
            workbook.write(out);
        }
    }

    /** 使用 OpenPDF 生成支持中文字体的 PDF 明细表。 */
    private void writePdf(Path target, String title, List<Map<String, Object>> rows) throws Exception {
        Document document = new Document(PageSize.A4.rotate(), 28, 28, 32, 32);
        try (OutputStream out = Files.newOutputStream(target)) {
            PdfWriter.getInstance(document, out);
            BaseFont baseFont = chineseFont();
            Font titleFont = new Font(baseFont, 16, Font.BOLD);
            Font bodyFont = new Font(baseFont, 10);
            Font headerFont = new Font(baseFont, 10, Font.BOLD);
            document.open();
            Paragraph heading = new Paragraph(title, titleFont);
            heading.setAlignment(Element.ALIGN_CENTER);
            heading.setSpacingAfter(8);
            document.add(heading);
            document.add(new Paragraph("导出时间：" + LocalDateTime.now().format(FMT_CN)
                    + "    记录总数：" + rows.size() + " 条", bodyFont));
            document.add(new Paragraph(" ", bodyFont));
            PdfPTable table = new PdfPTable(new float[]{1, 2.4f, 1.6f, 2f, 5f, 2.2f, 3.4f});
            table.setWidthPercentage(100);
            table.setHeaderRows(1);
            for (String header : List.of("序号", "植物名称", "植物编号", "养护项目", "养护说明", "操作人", "养护时间")) {
                PdfPCell cell = new PdfPCell(new com.lowagie.text.Phrase(header, headerFont));
                cell.setHorizontalAlignment(Element.ALIGN_CENTER);
                cell.setVerticalAlignment(Element.ALIGN_MIDDLE);
                cell.setBackgroundColor(new java.awt.Color(220, 242, 226));
                cell.setPadding(6);
                table.addCell(cell);
            }
            for (Map<String, Object> item : rows) {
                addPdfCell(table, item.get("sequence"), bodyFont, Element.ALIGN_CENTER);
                addPdfCell(table, item.get("plantName"), bodyFont, Element.ALIGN_LEFT);
                addPdfCell(table, item.get("plantId"), bodyFont, Element.ALIGN_CENTER);
                addPdfCell(table, item.get("type"), bodyFont, Element.ALIGN_CENTER);
                addPdfCell(table, item.get("note"), bodyFont, Element.ALIGN_LEFT);
                addPdfCell(table, item.get("operator"), bodyFont, Element.ALIGN_CENTER);
                addPdfCell(table, item.get("time"), bodyFont, Element.ALIGN_CENTER);
            }
            document.add(table);
            if (rows.isEmpty()) {
                Paragraph empty = new Paragraph("当前筛选条件下暂无养护记录。", bodyFont);
                empty.setSpacingBefore(10);
                document.add(empty);
            }
            document.close();
        }
    }

    private void addPdfCell(PdfPTable table, Object content, Font font, int alignment) {
        PdfPCell cell = new PdfPCell(new com.lowagie.text.Phrase(value(content), font));
        cell.setHorizontalAlignment(alignment);
        cell.setVerticalAlignment(Element.ALIGN_MIDDLE);
        cell.setPadding(5);
        table.addCell(cell);
    }

    private void setBorders(CellStyle style) {
        style.setBorderTop(BorderStyle.THIN);
        style.setBorderBottom(BorderStyle.THIN);
        style.setBorderLeft(BorderStyle.THIN);
        style.setBorderRight(BorderStyle.THIN);
    }

    private BaseFont chineseFont() throws Exception {
        // 优先嵌入本机 Unicode 字体，避免 PDF 换到手机或其他电脑后中文缺失。
        Path macFont = Paths.get("/Library/Fonts/Arial Unicode.ttf");
        if (Files.exists(macFont)) {
            return BaseFont.createFont(macFont.toString(), BaseFont.IDENTITY_H, BaseFont.EMBEDDED);
        }
        try {
            return BaseFont.createFont("STSong-Light", "UniGB-UCS2-H", BaseFont.NOT_EMBEDDED);
        } catch (Exception ignored) {
            // 非 macOS 环境没有中文字体时，最后回退到基础字体。
        }
        return BaseFont.createFont(BaseFont.HELVETICA, BaseFont.WINANSI, BaseFont.NOT_EMBEDDED);
    }

    private String value(Object value) {
        return value == null ? "" : String.valueOf(value);
    }
}
