"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import { ChevronRight, Code2, Download, Sparkles, User, Layout } from "lucide-react";
import { BrandLogoIcon } from "@/components/BrandLogo";
import {
  Chart,
  registerables,
  type ChartConfiguration,
  type ChartDataset,
  type ChartType,
  type Plugin,
  type TooltipItem,
} from "chart.js";

interface AnomalyItem {
  row_index: number;
  field: string;
  value: number;
  zscore: number;
  method: string;
}

interface AnomalyData {
  anomalies: AnomalyItem[];
  anomaly_indices: number[];
  summary: string;
  has_anomalies: boolean;
}

interface ForecastData {
  ts_labels: string[];
  ts_values: number[];
  value_key: string;
  label_key: string;
  forecast: number[];
  lower_ci: number[];
  upper_ci: number[];
  method: string;
  summary: string;
}

interface Message {
  role: string;
  content: string;
  viz_data?: string;
  status?: "streaming" | "complete";
  stage_label?: string;
  follow_ups?: string[];
  anomaly_data?: AnomalyData | null;
  forecast_data?: ForecastData | null;
}

function getNameInitials(name: string) {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (!words.length) {
    return "U";
  }

  return words
    .slice(0, 2)
    .map((word) => word.charAt(0).toUpperCase())
    .join("");
}

interface PlotlyTrace {
  type?: string;
  name?: string;
  x?: unknown;
  y?: unknown;
  labels?: unknown;
  values?: unknown;
  orientation?: string;
  fill?: string;
}

interface PlotlyLayoutAxis {
  title?: { text?: string } | string;
}

interface PlotlyLayout {
  title?: { text?: string } | string;
  xaxis?: PlotlyLayoutAxis;
  yaxis?: PlotlyLayoutAxis;
}

interface VizPayload {
  rows?: Array<Record<string, unknown>>;
  chart_type?: string;
  explanation?: string;
  query?: string;
  query_type?: string;
  viz_image?: string;
  viz_mime?: string;
  viz_filename?: string;
  viz_spec?: {
    data?: PlotlyTrace[];
    layout?: PlotlyLayout;
  };
}

const depthShadowPlugin: Plugin = {
  id: "depthShadow",
  beforeDatasetsDraw(chart) {
    const ctx = chart.ctx;
    ctx.save();
    ctx.shadowColor = "rgba(0, 0, 0, 0.45)";
    ctx.shadowBlur = 18;
    ctx.shadowOffsetX = 5;
    ctx.shadowOffsetY = 10;
  },
  afterDatasetsDraw(chart) {
    chart.ctx.restore();
  },
};

const threeDimensionalBarPlugin: Plugin = {
  id: "threeDimensionalBar",
  afterDatasetsDraw(chart, _args, options) {
    const config = options as { enabled?: boolean } | undefined;
    if (!config?.enabled || chart.options.indexAxis === "y") {
      return;
    }

    const ctx = chart.ctx;
    chart.data.datasets.forEach((_dataset, datasetIndex) => {
      const meta = chart.getDatasetMeta(datasetIndex);
      meta.data.forEach((element, index) => {
        const bar = element as unknown as { x: number; y: number; base: number; width: number };
        const dataset = chart.data.datasets[datasetIndex];
        const borderColor = Array.isArray(dataset.borderColor)
          ? String(dataset.borderColor[index] || dataset.borderColor[0] || "#1d4ed8")
          : String(dataset.borderColor || "#1d4ed8");
        const offset = Math.min(14, Math.max(6, bar.width * 0.18));
        const left = bar.x - bar.width / 2;
        const right = bar.x + bar.width / 2;
        const top = bar.y;
        const base = bar.base;

        ctx.save();
        ctx.fillStyle = borderColor;
        ctx.globalAlpha = 0.3;
        ctx.beginPath();
        ctx.moveTo(right, top);
        ctx.lineTo(right + offset, top - offset);
        ctx.lineTo(right + offset, base - offset);
        ctx.lineTo(right, base);
        ctx.closePath();
        ctx.fill();

        ctx.fillStyle = "rgba(255,255,255,0.28)";
        ctx.beginPath();
        ctx.moveTo(left, top);
        ctx.lineTo(right, top);
        ctx.lineTo(right + offset, top - offset);
        ctx.lineTo(left + offset, top - offset);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
      });
    });
  },
};

Chart.register(...registerables);
Chart.register(depthShadowPlugin);
Chart.register(threeDimensionalBarPlugin);

const DATASAGE_COLORS = {
  backgrounds: [
    "rgba(99, 102, 241, 0.82)",
    "rgba(16, 185, 129, 0.82)",
    "rgba(245, 158, 11, 0.82)",
    "rgba(239, 68, 68, 0.82)",
    "rgba(59, 130, 246, 0.82)",
    "rgba(168, 85, 247, 0.82)",
    "rgba(20, 184, 166, 0.82)",
    "rgba(251, 146, 60, 0.82)",
    "rgba(236, 72, 153, 0.82)",
    "rgba(132, 204, 22, 0.82)",
  ],
  borders: [
    "rgba(99, 102, 241, 1)",
    "rgba(16, 185, 129, 1)",
    "rgba(245, 158, 11, 1)",
    "rgba(239, 68, 68, 1)",
    "rgba(59, 130, 246, 1)",
    "rgba(168, 85, 247, 1)",
    "rgba(20, 184, 166, 1)",
    "rgba(251, 146, 60, 1)",
    "rgba(236, 72, 153, 1)",
    "rgba(132, 204, 22, 1)",
  ],
};

function getColors(count: number) {
  const bg: string[] = [];
  const br: string[] = [];
  for (let i = 0; i < count; i++) {
    bg.push(DATASAGE_COLORS.backgrounds[i % DATASAGE_COLORS.backgrounds.length]);
    br.push(DATASAGE_COLORS.borders[i % DATASAGE_COLORS.borders.length]);
  }
  return { bg, br };
}

function makeGradient(ctx: CanvasRenderingContext2D, canvasHeight: number, hexTop: string, hexBottom: string) {
  const grad = ctx.createLinearGradient(0, 0, 0, canvasHeight);
  grad.addColorStop(0, hexTop);
  grad.addColorStop(1, hexBottom);
  return grad;
}

/* ─── Text Rendering ─── */

const DECORATED_TOKEN_PATTERN =
  /("([^"\n]{1,40})"|'([^'\n]{1,40})'|(?:[$₹€£]\s?\d[\d,.]*(?:\.\d+)?%?)|(?:\b\d[\d,]*(?:\.\d+)?%?\b))/g;

const STREAM_CURSOR_TOKEN = "@@STREAM_CURSOR@@";

function renderStreamCursor(key: string) {
  return (
    <span key={key} className="message-stream-cursor" aria-hidden="true">
      ▍
    </span>
  );
}

function escapeForRegex(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function splitStreamingBlocks(content: string) {
  const normalized = content.replace(/\r\n/g, "\n");
  if (!normalized) {
    return { committedBlocks: [] as string[], tailBlock: "" };
  }

  const rawBlocks = normalized.split(/\n\s*\n/).filter(Boolean);
  if (/\n\s*\n$/.test(normalized)) {
    return { committedBlocks: rawBlocks, tailBlock: "" };
  }

  return {
    committedBlocks: rawBlocks.slice(0, -1),
    tailBlock: rawBlocks[rawBlocks.length - 1] ?? "",
  };
}

function getHighlightTone(text: string) {
  const value = text.trim();
  if (!value) return "keyword";
  if (value.length >= 34) return "headline";
  if (/[$₹€£]|\d|%/.test(value)) return "metric";
  if (/^#\d+/.test(value) || value.endsWith(":")) return "label";
  return "keyword";
}

function renderDecoratedPlainText(text: string, keyPrefix: string) {
  const blocks: React.ReactNode[] = [];
  const parts = text.split(STREAM_CURSOR_TOKEN);

  parts.forEach((part, partIndex) => {
    const matches = [...part.matchAll(DECORATED_TOKEN_PATTERN)];
    let cursor = 0;

    matches.forEach((match, index) => {
      const token = match[0];
      const start = match.index ?? 0;

      if (start > cursor) {
        blocks.push(
          <React.Fragment key={`${keyPrefix}-text-${partIndex}-${index}`}>
            {part.slice(cursor, start)}
          </React.Fragment>,
        );
      }

      const isQuoted =
        (token.startsWith('"') && token.endsWith('"')) || (token.startsWith("'") && token.endsWith("'"));

      if (isQuoted) {
        blocks.push(
          <span key={`${keyPrefix}-quote-${partIndex}-${index}`} className="message-chip">
            {token.slice(1, -1)}
          </span>,
        );
      } else {
        blocks.push(
          <span key={`${keyPrefix}-metric-${partIndex}-${index}`} className="message-data-token">
            {token}
          </span>,
        );
      }

      cursor = start + token.length;
    });

    if (cursor < part.length) {
      blocks.push(<React.Fragment key={`${keyPrefix}-tail-${partIndex}`}>{part.slice(cursor)}</React.Fragment>);
    }

    if (partIndex < parts.length - 1) {
      blocks.push(renderStreamCursor(`${keyPrefix}-cursor-${partIndex}`));
    }
  });

  return blocks.length ? blocks : text;
}

function renderInline(text: string) {
  const parts = text.split(/(\*\*.*?\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      const value = part.slice(2, -2);
      return (
        <span key={index} className={`message-highlight ${getHighlightTone(value)}`}>
          {value}
        </span>
      );
    }
    return <React.Fragment key={index}>{renderDecoratedPlainText(part, `inline-${index}`)}</React.Fragment>;
  });
}

function stripListMarker(line: string) {
  if (line.startsWith("- ") || line.startsWith("* ")) {
    return { kind: "unordered" as const, content: line.slice(2).trim() };
  }

  const orderedMatch = line.match(/^(\d+)\.\s+(.+)$/);
  if (orderedMatch) {
    return {
      kind: "ordered" as const,
      order: orderedMatch[1],
      content: orderedMatch[2].trim(),
    };
  }

  return null;
}

function renderMessageContent(content: string) {
  const lines = content.split("\n");
  const blocks: React.ReactNode[] = [];
  let listBuffer: Array<{ kind: "unordered" | "ordered"; content: string; order?: string }> = [];
  let paragraphBuffer: string[] = [];
  const cursorTokenPattern = new RegExp(`${escapeForRegex(STREAM_CURSOR_TOKEN)}$`);

  const flushLists = () => {
    if (!listBuffer.length) return;
    const isOrdered = listBuffer.every((item) => item.kind === "ordered");
    const ListTag = isOrdered ? "ol" : "ul";
    blocks.push(
      <ListTag
        key={`list-${blocks.length}`}
        className={`message-list ${isOrdered ? "message-list-ordered" : "message-list-unordered"}`}
      >
        {listBuffer.map((item, index) => (
          <li
            key={index}
            className={`message-list-item ${item.kind === "ordered" ? "message-list-item-ordered" : ""}`}
          >
            {item.kind === "ordered" ? <span className="message-list-number">{item.order}.</span> : null}
            <span className="message-list-copy">{renderInline(item.content)}</span>
          </li>
        ))}
      </ListTag>,
    );
    listBuffer = [];
  };

  const flushParagraph = () => {
    if (!paragraphBuffer.length) return;
    const joined = paragraphBuffer.join(" ");
    const joinedWithoutCursor = joined.replace(cursorTokenPattern, "");
    const hasCursor = joined !== joinedWithoutCursor;
    const leadMatch = joinedWithoutCursor.match(/^\*\*(.+?)\*\*\s+(.+)$/);

    if (leadMatch) {
      blocks.push(
        <p key={`paragraph-${blocks.length}`} className="message-lead">
          <span className="message-lead-badge">{leadMatch[1]}</span>
          <span className="message-lead-copy">
            {renderInline(hasCursor ? `${leadMatch[2]}${STREAM_CURSOR_TOKEN}` : leadMatch[2])}
          </span>
        </p>,
      );
      paragraphBuffer = [];
      return;
    }

    blocks.push(
      <p key={`paragraph-${blocks.length}`} className="message-paragraph">
        {renderInline(joined)}
      </p>,
    );
    paragraphBuffer = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushLists();
      flushParagraph();
      continue;
    }
    const listItem = stripListMarker(line);
    if (listItem) {
      flushParagraph();
      listBuffer.push(listItem);
      continue;
    }
    const sectionLine = line.replace(cursorTokenPattern, "");
    const sectionMatch = sectionLine.match(/^\*\*(.+?)\*\*$/);
    if (sectionMatch) {
      flushLists();
      flushParagraph();
      blocks.push(
        <div key={`section-${blocks.length}`} className="message-section-title">
          <span>
            {sectionMatch[1]}
            {sectionLine !== line ? renderStreamCursor(`section-cursor-${blocks.length}`) : null}
          </span>
        </div>,
      );
      continue;
    }
    flushLists();
    paragraphBuffer.push(line);
  }

  flushLists();
  flushParagraph();

  return blocks.length ? blocks : <p>{renderInline(content)}</p>;
}

function StreamingMessageContent({ content }: { content: string }) {
  const [streamRenderState, setStreamRenderState] = useState<{
    committedBlocks: Array<{ id: number; text: string }>;
    tailBlock: string;
  }>({ committedBlocks: [], tailBlock: "" });
  const processedContentRef = useRef("");
  const tailBlockRef = useRef("");
  const nextBlockIdRef = useRef(0);
  const rafIdRef = useRef<number | null>(null);
  const latestContentRef = useRef(content);

  const applyStreamingContent = useCallback((rawContent: string) => {
    const normalized = rawContent.replace(/\r\n/g, "\n");

    if (!normalized) {
      processedContentRef.current = "";
      tailBlockRef.current = "";
      nextBlockIdRef.current = 0;
      setStreamRenderState({ committedBlocks: [], tailBlock: "" });
      return;
    }

    if (!normalized.startsWith(processedContentRef.current)) {
      const rebuilt = splitStreamingBlocks(normalized);
      processedContentRef.current = normalized;
      tailBlockRef.current = rebuilt.tailBlock;
      nextBlockIdRef.current = rebuilt.committedBlocks.length;
      setStreamRenderState({
        committedBlocks: rebuilt.committedBlocks.map((text, index) => ({ id: index, text })),
        tailBlock: rebuilt.tailBlock,
      });
      return;
    }

    const delta = normalized.slice(processedContentRef.current.length);
    if (!delta) {
      return;
    }

    processedContentRef.current = normalized;
    const appended = splitStreamingBlocks(`${tailBlockRef.current}${delta}`);
    tailBlockRef.current = appended.tailBlock;

    if (!appended.committedBlocks.length) {
      setStreamRenderState((current) => ({ ...current, tailBlock: appended.tailBlock }));
      return;
    }

    const nextBlocks = appended.committedBlocks.map((text) => ({
      id: nextBlockIdRef.current++,
      text,
    }));

    setStreamRenderState((current) => ({
      committedBlocks: [...current.committedBlocks, ...nextBlocks],
      tailBlock: appended.tailBlock,
    }));
  }, []);

  useEffect(() => {
    latestContentRef.current = content;
    if (rafIdRef.current) {
      return;
    }

    rafIdRef.current = requestAnimationFrame(() => {
      rafIdRef.current = null;
      applyStreamingContent(latestContentRef.current);
    });

    return () => {
      if (rafIdRef.current) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    };
  }, [content, applyStreamingContent]);

  const committedBlocks = streamRenderState.committedBlocks;
  const tailBlock = streamRenderState.tailBlock;

  return (
    <div className="message-content message-content-streaming" aria-live="polite">
      {committedBlocks.map((block) => (
        <React.Fragment key={block.id}>{renderMessageContent(block.text)}</React.Fragment>
      ))}
      {tailBlock ? (
        <React.Fragment>{renderMessageContent(`${tailBlock}${STREAM_CURSOR_TOKEN}`)}</React.Fragment>
      ) : committedBlocks.length ? (
        <p className="message-paragraph">{renderStreamCursor("streaming-cursor")}</p>
      ) : null}
    </div>
  );
}

/* ─── Data Helpers ─── */

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function toArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function readTitle(value: unknown): string | undefined {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (isRecord(value) && typeof value.text === "string" && value.text.trim()) return value.text.trim();
  return undefined;
}

function compactDisplayValue(value: unknown, index = 0): string {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "number") return formatMetric(value);
  if (typeof value === "string" || typeof value === "boolean") return String(value);
  if (value instanceof Date) return value.toISOString();
  if (Array.isArray(value)) {
    const parts = value.map((item, itemIndex) => compactDisplayValue(item, itemIndex)).filter(Boolean);
    return parts.length ? parts.slice(0, 3).join(", ") : `Item ${index + 1}`;
  }
  if (isRecord(value)) {
    const preferredKeys = ["name", "title", "label", "category", "segment", "group", "status", "type", "method", "month", "date", "year"];
    for (const key of preferredKeys) {
      const nested = value[key];
      const display = compactDisplayValue(nested, index);
      if (display) return display;
    }

    if (value._id !== undefined && value._id !== value) {
      const display = compactDisplayValue(value._id, index);
      if (display) return display;
    }

    const entries = Object.entries(value)
      .map(([key, item]) => {
        const display = compactDisplayValue(item, index);
        return display ? `${humanizeFieldName(key)}: ${display}` : "";
      })
      .filter(Boolean);
    return entries.length ? entries.slice(0, 3).join(", ") : `Item ${index + 1}`;
  }
  return String(value);
}

function toLabel(value: unknown, index: number) {
  const label = compactDisplayValue(value, index).trim();
  return label || `Item ${index + 1}`;
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

function humanizeFieldName(value: string) {
  const normalized = value
    .replace(/[_-]+/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/\s+/g, " ")
    .trim();
  if (!normalized) return value;
  return normalized.replace(/\b\w/g, (c) => c.toUpperCase());
}

function isIdentifierColumn(value: string) {
  const n = value.trim().toLowerCase();
  return (
    n === "id" ||
    n === "_id" ||
    n === "unnamed: 0" ||
    n === "code" ||
    n === "key" ||
    n.endsWith("_id") ||
    n.startsWith("id_") ||
    n.endsWith("_code") ||
    n.startsWith("code_") ||
    n.endsWith("_key") ||
    n.startsWith("key_")
  );
}

function getEntityTokens(value: string) {
  return value
    .trim()
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((token) => token && !["id", "ids", "code", "codes", "key", "keys", "uuid", "guid", "number", "numbers", "no"].includes(token));
}

function hasReadableCompanionColumn(columns: string[], identifierColumn: string) {
  const identifierTokens = new Set(getEntityTokens(identifierColumn));
  return columns.some((column) => {
    if (column === identifierColumn || isIdentifierColumn(column)) return false;
    const lowered = column.trim().toLowerCase();
    const columnTokens = getEntityTokens(column);
    const sharesEntityToken = columnTokens.some((token) => identifierTokens.has(token));
    const isReadable = /(name|title|label|category|segment|group|description)/i.test(lowered);
    return sharesEntityToken && isReadable;
  });
}

function getUserFacingColumns(columns: string[]) {
  const withoutIndex = columns.filter((c) => c.trim().toLowerCase() !== "unnamed: 0");
  const withoutId = withoutIndex.filter((c) => !isIdentifierColumn(c) || !hasReadableCompanionColumn(withoutIndex, c));
  return withoutId.length ? withoutId : withoutIndex;
}

function prettifyTitle(value: string) {
  if (/_|-/.test(value) || /[a-z][A-Z]/.test(value)) return humanizeFieldName(value);
  return value;
}

function formatMetric(value: number) {
  return new Intl.NumberFormat("en-US", {
    notation: Math.abs(value) >= 1000 ? "compact" : "standard",
    maximumFractionDigits: Math.abs(value) >= 1000 ? 1 : 2,
  }).format(value);
}

function formatAxisTick(value: unknown) {
  const n = toNumber(value);
  return n === null ? String(value ?? "") : formatMetric(n);
}

function formatRangeLabel(start: number, end: number) {
  return `${formatMetric(start)}-${formatMetric(end)}`;
}

const SEMANTIC_LABEL_PATTERN = /\b(label|name|title|category|segment|group|bucket|stage|month|date|time|period|year|week|day|quarter)\b/i;
const PLACEHOLDER_LABEL_PATTERN = /^(item|point|row|value|series)\s+\d+$/i;
const PLACEHOLDER_DATASET_PATTERN = /^(label|value|count|series \d+|metric value|metric name|__label__|__count__|range)$/i;

function isSemanticLabelColumn(value: string) {
  return SEMANTIC_LABEL_PATTERN.test(value);
}

function isPlaceholderLabel(value: string) {
  return PLACEHOLDER_LABEL_PATTERN.test(value.trim());
}

function isPlaceholderDatasetName(value: string) {
  return PLACEHOLDER_DATASET_PATTERN.test(value.trim());
}

function hasUsableColumnValues(values: unknown[]) {
  const normalized = values
    .map((value) => String(value ?? "").trim())
    .filter(Boolean);
  return new Set(normalized).size >= 2;
}

/* ─── Chart Building ─── */

function inferChartType(chartType: string | undefined, traces: PlotlyTrace[]) {
  if (chartType) return chartType.toLowerCase();
  const firstTrace = traces[0];
  if (!firstTrace?.type) return "table";
  if (firstTrace.type === "scatter" && firstTrace.fill && firstTrace.fill !== "none") return "area";
  return firstTrace.type.toLowerCase();
}

function buildCartesianSeries(traces: PlotlyTrace[]) {
  const rows = new Map<string, Record<string, string | number>>();
  const order: string[] = [];
  const seriesKeys: string[] = [];
  let isHorizontal = false;

  traces.forEach((trace, index) => {
    const rawValues = toArray(trace.orientation === "h" ? trace.x : trace.y);
    const rawCategories = toArray(trace.orientation === "h" ? trace.y : trace.x);
    const categories = rawCategories.length ? rawCategories : rawValues.map((_, i) => i + 1);

    if (!rawValues.length) return;

    isHorizontal = isHorizontal || trace.orientation === "h";
    const seriesKey =
      typeof trace.name === "string" && trace.name.trim()
        ? humanizeFieldName(trace.name.trim())
        : traces.length === 1
          ? "Value"
          : `Series ${index + 1}`;

    if (!seriesKeys.includes(seriesKey)) seriesKeys.push(seriesKey);

    const pointCount = Math.min(categories.length, rawValues.length);
    for (let i = 0; i < pointCount; i++) {
      const numericValue = toNumber(rawValues[i]);
      if (numericValue === null) continue;

      const label = toLabel(categories[i], i);
      if (!rows.has(label)) {
        rows.set(label, { label });
        order.push(label);
      }
      rows.get(label)![seriesKey] = numericValue;
    }
  });

  if (!order.length || !seriesKeys.length) return null;

  return {
    data: order.map((label) => rows.get(label)!),
    isHorizontal,
    seriesKeys,
  };
}

function buildScatterSeries(traces: PlotlyTrace[]) {
  const firstTrace = traces[0];
  if (!firstTrace) return null;
  const xs = toArray(firstTrace.x);
  const ys = toArray(firstTrace.y);
  const data: Array<{ x: number; y: number }> = [];
  const pointCount = Math.min(xs.length, ys.length);
  for (let i = 0; i < pointCount; i++) {
    const x = toNumber(xs[i]);
    const y = toNumber(ys[i]);
    if (x === null || y === null) continue;
    data.push({ x, y });
  }
  return data.length ? data : null;
}

function buildHistogramSeries(traces: PlotlyTrace[]) {
  const firstTrace = traces[0];
  if (!firstTrace) return null;
  const sourceValues = toArray(firstTrace.x).length ? toArray(firstTrace.x) : toArray(firstTrace.y);
  const numericValues = sourceValues.map((v) => toNumber(v)).filter((v): v is number => v !== null);
  if (!numericValues.length) return null;

  const minValue = Math.min(...numericValues);
  const maxValue = Math.max(...numericValues);
  const bucketCount = Math.max(6, Math.min(12, Math.ceil(Math.sqrt(numericValues.length))));

  if (minValue === maxValue) return [{ label: String(minValue), Value: numericValues.length }];

  const bucketSize = (maxValue - minValue) / bucketCount;
  const buckets = Array.from({ length: bucketCount }, (_, i) => ({
    label: `${(minValue + bucketSize * i).toFixed(1)}–${(minValue + bucketSize * (i + 1)).toFixed(1)}`,
    Value: 0,
  }));

  numericValues.forEach((v) => {
    const bi = Math.min(bucketCount - 1, Math.floor((v - minValue) / bucketSize));
    buckets[bi].Value += 1;
  });

  return buckets;
}

function getFrameHeight(chartType: string, itemCount: number, isHorizontal = false) {
  if (chartType === "bar" && isHorizontal) return Math.min(820, Math.max(320, itemCount * 36 + 80));
  if (chartType === "pie") return 360;
  if (chartType === "scatter") return 380;
  return 320;
}

type DataSageChartType = "bar" | "threeDBar" | "horizontalBar" | "groupedBar" | "line" | "donut" | "histogram" | "radar";
type RenderChartType = DataSageChartType;

type DataSageDataset = {
  label: string;
  data: number[];
  backgroundColor?: string | string[] | CanvasGradient;
  borderColor?: string | string[];
  borderWidth?: number;
  borderRadius?: number;
  fill?: boolean;
  pointBackgroundColor?: string;
  pointBorderColor?: string;
  tension?: number;
};

interface NormalizedChartData {
  labels: string[];
  datasets: DataSageDataset[];
  columnNames: string[];
  numericColumnNames: string[];
  rowCount: number;
  sourceRows?: Array<Record<string, unknown>>;
  labelColumn?: string;
  sameEntityNumericDimensions?: boolean;
}

const TIME_COLUMN_PATTERN = /(date|time|month|year|week|day|quarter|period)/i;
const CHART_TYPE_OPTIONS: Array<{ value: DataSageChartType; label: string }> = [
  { value: "bar", label: "Bar chart" },
  { value: "threeDBar", label: "3D bar chart" },
  { value: "horizontalBar", label: "Horizontal bar chart" },
  { value: "groupedBar", label: "Grouped bar chart" },
  { value: "line", label: "Line chart" },
  { value: "donut", label: "Donut chart" },
  { value: "histogram", label: "Histogram" },
  { value: "radar", label: "Radar chart" },
];
const chartCursorHandlers = new WeakMap<HTMLCanvasElement, (event: MouseEvent) => void>();

function toChartNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return null;

  const trimmed = value.trim();
  if (!trimmed) return null;

  const cleaned = trimmed.replace(/[$₹€£,%\s,]/g, "");
  const numericValue = Number(cleaned);
  if (Number.isFinite(numericValue)) return numericValue;

  const parsed = parseFloat(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

function makeDataSet(label: string, values: unknown[]): DataSageDataset {
  return {
    label: humanizeFieldName(label || "Value"),
    data: values.map((value) => toChartNumber(value) ?? Number.NaN),
  };
}

function emptyNormalizedChartData(): NormalizedChartData {
  return { labels: [], datasets: [{ label: "No Data", data: [] }], columnNames: [], numericColumnNames: [], rowCount: 0 };
}

function isTimeColumnName(columnName: string) {
  return TIME_COLUMN_PATTERN.test(columnName);
}

function findLabelKey(keys: string[], rows: Array<Record<string, unknown>>) {
  const timeKey = keys.find(isTimeColumnName);
  if (timeKey) return timeKey;

  const numericKeys = keys.filter((key) => rows.some((row) => toChartNumber(row[key]) !== null));
  const identifierKey = keys.find((key) => isIdentifierColumn(key));
  if (identifierKey && numericKeys.some((key) => key !== identifierKey)) {
    return identifierKey;
  }

  const semanticKey = keys.find(
    (key) =>
      !isIdentifierColumn(key) &&
      isSemanticLabelColumn(key) &&
      hasUsableColumnValues(rows.map((row) => row[key])),
  );
  if (semanticKey) return semanticKey;

  return (
    keys.find(
      (key) =>
        !isIdentifierColumn(key) &&
        rows.some((row) => {
          const value = row[key];
          return value !== null && value !== undefined && value !== "" && toChartNumber(value) === null;
        }),
    ) ||
    keys.find((key) =>
      rows.some((row) => {
        const value = row[key];
        return value !== null && value !== undefined && value !== "" && toChartNumber(value) === null;
      }),
    )
  );
}

function findLabelColumnIndex(columns: string[], rows: unknown[][]) {
  const timeIndex = columns.findIndex(isTimeColumnName);
  if (timeIndex >= 0) return timeIndex;

  const numericIndexes = columns
    .map((_, index) => index)
    .filter((index) => rows.some((row) => toChartNumber(row[index]) !== null));
  const identifierIndex = columns.findIndex(isIdentifierColumn);
  if (identifierIndex >= 0 && numericIndexes.some((index) => index !== identifierIndex)) {
    return identifierIndex;
  }

  const semanticIndex = columns.findIndex(
    (columnName, columnIndex) =>
      !isIdentifierColumn(columnName) &&
      isSemanticLabelColumn(columnName) &&
      hasUsableColumnValues(rows.map((row) => row[columnIndex])),
  );
  if (semanticIndex >= 0) return semanticIndex;

  return columns.findIndex((_, columnIndex) =>
    rows.some((row) => {
      const value = row[columnIndex];
      return value !== null && value !== undefined && value !== "" && toChartNumber(value) === null;
    }),
  );
}

function normalizeRecordRows(rows: Array<Record<string, unknown>>): NormalizedChartData {
  if (!rows.length) return emptyNormalizedChartData();

  const keys = Object.keys(rows[0]);
  const labelKey = findLabelKey(keys, rows);
  const numericKeys = keys.filter((key) => key !== labelKey && rows.some((row) => toChartNumber(row[key]) !== null));
  const valueKeys = numericKeys;

  // When there is no label column (all columns are numeric), pivot the data:
  // use humanized column names as X-axis labels so bars are named instead of "Item 1"
  if (!labelKey && numericKeys.length >= 2 && rows.length <= 3) {
    const pivotedLabels = numericKeys.map(humanizeFieldName);
    const pivotedData = rows.map((_, rowIndex) =>
      numericKeys.map((key) => toChartNumber(rows[rowIndex][key]) ?? Number.NaN)
    );
    return {
      labels: pivotedLabels,
      datasets:
        rows.length === 1
          ? [{ label: "Value", data: pivotedData[0] }]
          : rows.map((_, rowIndex) => ({ label: `Row ${rowIndex + 1}`, data: pivotedData[rowIndex] })),
      columnNames: numericKeys,
      numericColumnNames: numericKeys,
      rowCount: pivotedLabels.length,
      sourceRows: rows,
      labelColumn: undefined,
      sameEntityNumericDimensions: numericKeys.length >= 3,
    };
  }

  const labels = labelKey ? rows.map((row, index) => toLabel(row[labelKey], index)) : rows.map((_, index) => `Item ${index + 1}`);

  if (!valueKeys.length) return emptyNormalizedChartData();

  return {
    labels,
    datasets: valueKeys.map((key) => makeDataSet(key, rows.map((row) => row[key]))),
    columnNames: labelKey ? [labelKey, ...valueKeys] : valueKeys,
    numericColumnNames: numericKeys.length ? numericKeys : valueKeys,
    rowCount: rows.length,
    sourceRows: rows,
    labelColumn: labelKey,
    sameEntityNumericDimensions: rows.length === 1 && numericKeys.length >= 3,
  };
}

function normalizeSqlRows(columns: unknown[], rows: unknown[][]): NormalizedChartData {
  const columnNames = columns.map((column, index) => String(column || `Column ${index + 1}`));
  const labelIndex = findLabelColumnIndex(columnNames, rows);
  const numericIndexes = columnNames
    .map((_, index) => index)
    .filter((index) => index !== labelIndex && rows.some((row) => toChartNumber(row[index]) !== null));
  const valueIndexes = numericIndexes;

  // When there is no label column (all columns are numeric), pivot the data:
  // use humanized column names as X-axis labels so bars are named instead of "Item 1"
  if (labelIndex < 0 && numericIndexes.length >= 2 && rows.length <= 3) {
    const pivotedLabels = numericIndexes.map((index) => humanizeFieldName(columnNames[index]));
    const pivotedData = rows.map((row) =>
      numericIndexes.map((index) => toChartNumber(row[index]) ?? Number.NaN)
    );
    return {
      labels: pivotedLabels,
      datasets:
        rows.length === 1
          ? [{ label: "Value", data: pivotedData[0] }]
          : rows.map((_, rowIndex) => ({ label: `Row ${rowIndex + 1}`, data: pivotedData[rowIndex] })),
      columnNames: numericIndexes.map((index) => columnNames[index]),
      numericColumnNames: numericIndexes.map((index) => columnNames[index]),
      rowCount: pivotedLabels.length,
      sameEntityNumericDimensions: numericIndexes.length >= 3,
    };
  }

  const labels =
    labelIndex >= 0 ? rows.map((row, index) => toLabel(row[labelIndex], index)) : rows.map((_, index) => `Item ${index + 1}`);

  if (!valueIndexes.length) return emptyNormalizedChartData();

  return {
    labels,
    datasets: valueIndexes.map((index) => makeDataSet(columnNames[index], rows.map((row) => row[index]))),
    columnNames:
      labelIndex >= 0
        ? [columnNames[labelIndex], ...valueIndexes.map((index) => columnNames[index])]
        : valueIndexes.map((index) => columnNames[index]),
    numericColumnNames: numericIndexes.length ? numericIndexes.map((index) => columnNames[index]) : valueIndexes.map((index) => columnNames[index]),
    rowCount: rows.length,
    sameEntityNumericDimensions: rows.length === 1 && numericIndexes.length >= 3,
  };
}

function normalizeChartData(rawData: unknown): NormalizedChartData {
  let labels: string[] = [];
  let datasets: DataSageDataset[] = [];

  try {
    if (isRecord(rawData) && Array.isArray(rawData.datasets) && Array.isArray(rawData.labels)) {
      labels = rawData.labels.map((label, index) => toLabel(label, index));
      datasets = rawData.datasets
        .filter(isRecord)
        .map((dataset, index) => makeDataSet(typeof dataset.label === "string" ? dataset.label : `Series ${index + 1}`, toArray(dataset.data)))
        .filter((dataset) => dataset.data.some((value) => Number.isFinite(value)));
      if (!datasets.length) return emptyNormalizedChartData();
      return {
        labels,
        datasets,
        columnNames: datasets.length === 1 ? ["label", datasets[0].label] : ["label", ...datasets.map((dataset) => dataset.label)],
        numericColumnNames: datasets.map((dataset) => dataset.label),
        rowCount: labels.length,
        sameEntityNumericDimensions: labels.length <= 1 && datasets.length >= 3,
      };
    }

    if (isRecord(rawData) && Array.isArray(rawData.labels) && Array.isArray(rawData.values)) {
      labels = rawData.labels.map((label, index) => toLabel(label, index));
      datasets = [makeDataSet("Value", rawData.values)];
      if (!datasets[0].data.some((value) => Number.isFinite(value))) return emptyNormalizedChartData();
      return { labels, datasets, columnNames: ["label", "value"], numericColumnNames: ["value"], rowCount: labels.length };
    }

    if (isRecord(rawData) && Array.isArray(rawData.columns) && Array.isArray(rawData.rows)) {
      return normalizeSqlRows(rawData.columns, rawData.rows.filter(Array.isArray));
    }

    if (Array.isArray(rawData) && Array.isArray(rawData[0])) {
      const [headers, ...rows] = rawData as unknown[][];
      return normalizeSqlRows(headers, rows.filter(Array.isArray));
    }

    if (Array.isArray(rawData) && isRecord(rawData[0])) {
      return normalizeRecordRows(rawData.filter(isRecord));
    }
  } catch (err) {
    console.error("normalizeChartData error:", err);
  }

  return emptyNormalizedChartData();
}

function scoreNormalizedChartData(data: NormalizedChartData) {
  let score = 0;

  if (hasChartableData(data)) score += 10;
  if (data.labelColumn) score += 4;
  if (data.labels.some((label) => !isPlaceholderLabel(label))) score += 4;
  if (data.labels.every((label) => isPlaceholderLabel(label))) score -= 6;
  if (data.labels.some((label) => /\d{4}[-/]/.test(label) || /[A-Za-z]{3,}/.test(label))) score += 2;
  if (data.datasets.every((dataset) => !isPlaceholderDatasetName(dataset.label))) score += 3;
  if (data.datasets.some((dataset) => isPlaceholderDatasetName(dataset.label))) score -= 4;
  if (data.datasets.length > 1) score += 1;

  return score;
}

function pickBestRawChartData(
  rows: Array<Record<string, unknown>>,
  traces: PlotlyTrace[],
): unknown | null {
  const rowData: unknown = rows.length ? rows : null;
  const traceData: unknown = traces.length ? plotlyTracesToRawData(traces) : null;

  if (rowData && traceData) {
    const rowScore = scoreNormalizedChartData(normalizeChartData(rowData));
    const traceScore = scoreNormalizedChartData(normalizeChartData(traceData));
    return traceScore > rowScore ? traceData : rowData;
  }

  return rowData || traceData;
}

function selectChartType(data: NormalizedChartData, query: string): DataSageChartType {
  const q = query.toLowerCase();
  const rowCount = data.rowCount || data.labels.length;
  const hasTimeColumn = data.columnNames.some(isTimeColumnName);
  const numericDimensionCount = Math.max(data.numericColumnNames.length, data.datasets.length);
  const hasTwoColumns = data.columnNames.length === 2 || (data.datasets.length === 1 && data.labels.length > 0);
  const asksForGenericGraph =
    /\b(graph|chart|plot|visual|visualization)\b/.test(q) &&
    !/\b(pie|donut|doughnut|breakdown|share|proportion|percentage)\b/.test(q);

  if (/\b3d\b|\bthree[- ]d\b|\bthree dimensional\b/.test(q)) return "threeDBar";
  if (/\b(distribution|spread|range|frequency)\b/.test(q)) return "histogram";
  if (/\b(trend|growth|change|history)\b/.test(q) || q.includes("over time") || hasTimeColumn) return "line";
  if (/\b(compare|vs|versus|rank|top|bottom)\b/.test(q)) return "horizontalBar";
  if (/\b(pie|donut|doughnut|breakdown|share|proportion|percentage)\b/.test(q)) return "donut";
  if (data.sameEntityNumericDimensions || (rowCount <= 1 && numericDimensionCount >= 3)) return "radar";
  if (numericDimensionCount >= 3) return "groupedBar";
  if (asksForGenericGraph) return rowCount > 10 ? "horizontalBar" : "bar";
  if (hasTwoColumns && rowCount <= 8) return "donut";
  if (hasTwoColumns && rowCount > 8) return "horizontalBar";
  return "bar";
}

function mapPreferredChartType(chartType: string | undefined): DataSageChartType | null {
  const normalized = (chartType || "").toLowerCase();
  if (!normalized) return null;
  if (normalized === "3d_bar" || normalized === "three_d_bar" || normalized === "3dbar") return "threeDBar";
  if (normalized === "pie") return "donut";
  if (normalized === "line" || normalized === "area") return "line";
  if (normalized === "histogram" || normalized === "histogram_grid") return "histogram";
  if (normalized === "bar" || normalized === "funnel") return "bar";
  return null;
}

function resolveInitialChartType(
  normalized: NormalizedChartData,
  userQuery: string,
  preferredChartType?: DataSageChartType | null,
): DataSageChartType {
  const inferred = preferredChartType || selectChartType(normalized, userQuery);
  if (inferred === "threeDBar" && normalized.labels.length > 12) {
    return "horizontalBar";
  }
  return inferred;
}

function plotlyTracesToRawData(traces: PlotlyTrace[]) {
  const pieTrace = traces.find((trace) => trace.type?.toLowerCase() === "pie");
  if (pieTrace) {
    return { labels: toArray(pieTrace.labels), values: toArray(pieTrace.values) };
  }

  const histogramTrace = traces.find((trace) => trace.type?.toLowerCase() === "histogram");
  if (histogramTrace) {
    const values = toArray(histogramTrace.x).length ? toArray(histogramTrace.x) : toArray(histogramTrace.y);
    return { labels: values.map((_, index) => `Item ${index + 1}`), values };
  }

  const rows = new Map<string, Record<string, unknown>>();
  const order: string[] = [];
  const seriesNames: string[] = [];

  traces.forEach((trace, traceIndex) => {
    const values = toArray(trace.orientation === "h" ? trace.x : trace.y);
    const categories = toArray(trace.orientation === "h" ? trace.y : trace.x);
    const labels = categories.length ? categories : values.map((_, index) => `Item ${index + 1}`);
    const seriesName =
      typeof trace.name === "string" && trace.name.trim()
        ? trace.name.trim()
        : traces.length === 1
          ? "Value"
          : `Series ${traceIndex + 1}`;

    if (!seriesNames.includes(seriesName)) {
      seriesNames.push(seriesName);
    }

    for (let index = 0; index < Math.min(labels.length, values.length); index++) {
      const label = toLabel(labels[index], index);
      if (!rows.has(label)) {
        rows.set(label, { label });
        order.push(label);
      }
      rows.get(label)![seriesName] = values[index];
    }
  });

  if (!order.length) return null;
  return order.map((label) => rows.get(label)!);
}

function hasChartableData(data: NormalizedChartData) {
  return Boolean(data.labels.length && data.datasets.some((dataset) => dataset.data.some((value) => Number.isFinite(value))));
}

function cloneChartData(data: NormalizedChartData): NormalizedChartData {
  return {
    ...data,
    labels: [...data.labels],
    datasets: data.datasets.map((dataset) => ({ ...dataset, data: [...dataset.data] })),
  };
}

function buildHistogramChartData(data: NormalizedChartData): NormalizedChartData {
  const numericValues = data.datasets.flatMap((dataset) => dataset.data).filter((value) => Number.isFinite(value));
  if (!numericValues.length) return cloneChartData(data);

  const minValue = Math.min(...numericValues);
  const maxValue = Math.max(...numericValues);
  if (minValue === maxValue) {
    return {
      ...data,
      labels: [String(minValue)],
      datasets: [{ label: "Frequency", data: [numericValues.length] }],
    };
  }

  const bucketCount = Math.max(6, Math.min(12, Math.ceil(Math.sqrt(numericValues.length))));
  const bucketSize = (maxValue - minValue) / bucketCount;
  const buckets = Array.from({ length: bucketCount }, (_, index) => ({
    label: formatRangeLabel(minValue + bucketSize * index, minValue + bucketSize * (index + 1)),
    count: 0,
  }));

  numericValues.forEach((value) => {
    const bucketIndex = Math.min(bucketCount - 1, Math.floor((value - minValue) / bucketSize));
    buckets[bucketIndex].count += 1;
  });

  return {
    ...data,
    labels: buckets.map((bucket) => bucket.label),
    datasets: [{ label: "Frequency", data: buckets.map((bucket) => bucket.count) }],
  };
}

function buildRadarChartData(data: NormalizedChartData): NormalizedChartData {
  if (data.sourceRows?.length && data.numericColumnNames.length >= 3) {
    const rows = data.sourceRows.slice(0, 4);
    return {
      ...data,
      labels: data.numericColumnNames.map(humanizeFieldName),
      datasets: rows.map((row, index) => ({
        label: data.labelColumn ? toLabel(row[data.labelColumn], index) : `Entity ${index + 1}`,
        data: data.numericColumnNames.map((columnName) => toChartNumber(row[columnName]) ?? 0),
      })),
    };
  }

  if (data.datasets.length >= 3) {
    return {
      ...data,
      labels: data.datasets.map((dataset) => dataset.label),
      datasets: data.labels.slice(0, 4).map((label, labelIndex) => ({
        label,
        data: data.datasets.map((dataset) => dataset.data[labelIndex] ?? 0),
      })),
    };
  }

  return cloneChartData(data);
}

function prepareChartData(data: NormalizedChartData, chartType: RenderChartType): NormalizedChartData {
  if (chartType === "histogram") return buildHistogramChartData(data);
  if (chartType === "radar") return buildRadarChartData(data);
  return cloneChartData(data);
}

function toChartJsType(chartType: RenderChartType): ChartType {
  if (chartType === "donut") return "doughnut";
  if (chartType === "line") return "line";
  if (chartType === "radar") return "radar";
  return "bar";
}

function getChartFrameHeight(chartType: RenderChartType, itemCount: number) {
  if (chartType === "horizontalBar") return Math.min(980, Math.max(560, itemCount * 54 + 160));
  if (chartType === "donut" || chartType === "radar") return 560;
  return 520;
}

function getChartAspectRatio(chartType: RenderChartType, itemCount: number) {
  if (chartType === "horizontalBar") return Math.max(1.15, Math.min(1.65, 720 / Math.max(420, itemCount * 54 + 160)));
  if (chartType === "donut" || chartType === "radar") return 1.2;
  return 1.65;
}

function cleanupChartCanvas(canvas: HTMLCanvasElement) {
  const existing = Chart.getChart(canvas);
  if (existing) existing.destroy();

  const existingHandler = chartCursorHandlers.get(canvas);
  if (existingHandler) {
    canvas.removeEventListener("mousemove", existingHandler);
    chartCursorHandlers.delete(canvas);
  }
  canvas.style.cursor = "default";
}

function getTooltipConfig() {
  return {
    enabled: true,
    backgroundColor: "rgba(10, 10, 30, 0.93)",
    borderColor: "rgba(99, 102, 241, 0.75)",
    borderWidth: 1,
    titleColor: "#a5b4fc",
    bodyColor: "#e2e8f0",
    footerColor: "#94a3b8",
    padding: 14,
    cornerRadius: 12,
    displayColors: true,
    boxWidth: 12,
    boxHeight: 12,
    boxPadding: 4,
    caretSize: 8,
    usePointStyle: true,
    callbacks: {
      title: (items: TooltipItem<ChartType>[]) => `  ${items[0].label}`,
      label: (item: TooltipItem<ChartType>) => {
        const val = item.formattedValue;
        const label = item.dataset.label || "Value";
        return `  ${label}: ${val}`;
      },
      footer: (items: TooltipItem<ChartType>[]) => {
        const item = items[0];
        const data = (Array.isArray(item.dataset.data) ? item.dataset.data : []) as unknown[];
        const total = data.reduce<number>((sum, value) => sum + (parseFloat(String(value)) || 0), 0);
        if (total === 0) return "";
        const rawValue = typeof item.raw === "number" ? item.raw : parseFloat(String(item.raw)) || 0;
        const pct = ((rawValue / total) * 100).toFixed(1);
        return `  Share: ${pct}%`;
      },
    },
  };
}

function applyDatasetColors(
  datasets: DataSageDataset[],
  chartType: RenderChartType,
  ctx: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  labelCount: number,
) {
  const { bg, br } = getColors(Math.max(labelCount, datasets.length, 1));
  const canvasHeight = canvas.height || canvas.clientHeight || 360;

  datasets.forEach((dataset, index) => {
    const singleBg = DATASAGE_COLORS.backgrounds[index % DATASAGE_COLORS.backgrounds.length];
    const singleBr = DATASAGE_COLORS.borders[index % DATASAGE_COLORS.borders.length];
    const isLine = chartType === "line";
    const isRadial = chartType === "donut" || chartType === "radar";
    const isBar =
      chartType === "bar" ||
      chartType === "threeDBar" ||
      chartType === "groupedBar" ||
      chartType === "horizontalBar" ||
      chartType === "histogram";

    if (datasets.length === 1 && !isLine) {
      dataset.backgroundColor = isRadial ? bg : bg;
      dataset.borderColor = br;
    } else {
      dataset.backgroundColor =
        isLine || isBar ? makeGradient(ctx, canvasHeight, singleBg, "rgba(15, 23, 42, 0.08)") : singleBg;
      dataset.borderColor = singleBr;
    }

    if (chartType === "radar") {
      dataset.backgroundColor = singleBg.replace("0.82", "0.24");
      dataset.pointBackgroundColor = singleBr;
      dataset.pointBorderColor = "#ffffff";
    }

    if (isLine) {
      dataset.backgroundColor = makeGradient(ctx, canvasHeight, singleBg, "rgba(0,0,0,0)");
      dataset.fill = true;
      dataset.tension = 0.42;
      dataset.pointBackgroundColor = singleBr;
      dataset.pointBorderColor = "#ffffff";
    }

    dataset.borderWidth = isLine ? 3 : 2;
    dataset.borderRadius = isBar ? 6 : 0;
  });
}

function buildChartOptions(chartType: RenderChartType, itemCount: number): ChartConfiguration<ChartType, number[], string>["options"] {
  const usesScales = ["bar", "threeDBar", "line", "horizontalBar", "histogram", "groupedBar"].includes(chartType);
  const isHorizontal = chartType === "horizontalBar";
  const isLine = chartType === "line";
  const truncateTick = (value: string) => (value.length > 18 ? `${value.slice(0, 17)}...` : value);
  const plugins = {
    tooltip: getTooltipConfig(),
    legend: {
      display: !["bar", "threeDBar", "horizontalBar", "histogram"].includes(chartType),
      labels: {
        color: "#475569",
        usePointStyle: true,
        padding: 18,
        font: { size: 13 },
      },
    },
  } as NonNullable<ChartConfiguration<ChartType, number[], string>["options"]>["plugins"] & {
    threeDimensionalBar?: { enabled: boolean };
  };

  plugins.threeDimensionalBar = {
    enabled: chartType === "threeDBar",
  };

  return {
    responsive: true,
    maintainAspectRatio: false,
    layout: {
      padding: chartType === "threeDBar" ? { top: 26, right: 34, bottom: 10, left: 8 } : { top: 12, right: 14, bottom: 8, left: 4 },
    },
    indexAxis: isHorizontal ? "y" : "x",
    aspectRatio: getChartAspectRatio(chartType, itemCount),
    animation: {
      duration: 1100,
      easing: "easeInOutQuart",
      delay: (ctx: { type: string; dataIndex: number }) => (ctx.type === "data" ? ctx.dataIndex * 80 : 0),
    },
    transitions: {
      active: { animation: { duration: 250 } },
    },
    elements: isLine
      ? {
          line: {
            tension: 0.42,
            fill: true,
            borderWidth: 3,
          },
          point: {
            radius: 5,
            hoverRadius: 9,
            hoverBorderWidth: 2,
            hitRadius: 12,
          },
        }
      : undefined,
    plugins,
    scales: usesScales
      ? {
          x: {
            grid: { color: "rgba(15,23,42,0.08)" },
            ticks: {
              color: "#64748b",
              autoSkip: !isHorizontal && itemCount > 10,
              maxTicksLimit: isHorizontal ? undefined : 10,
              maxRotation: isHorizontal ? 0 : 38,
              minRotation: isHorizontal ? 0 : itemCount > 8 ? 28 : 0,
              callback(value) {
                const label = isHorizontal ? formatAxisTick(value) : this.getLabelForValue(Number(value));
                return truncateTick(String(label));
              },
            },
            beginAtZero: isHorizontal,
            grace: isHorizontal ? "8%" : undefined,
          },
          y: {
            grid: { color: "rgba(15,23,42,0.08)" },
            ticks: {
              color: "#64748b",
              callback(value) {
                return isHorizontal ? truncateTick(this.getLabelForValue(Number(value))) : formatAxisTick(value);
              },
            },
            beginAtZero: !isHorizontal,
            grace: isHorizontal ? undefined : "12%",
          },
        }
      : {},
  };
}

function resolveChartCanvas(containerSelector: string | HTMLCanvasElement): HTMLCanvasElement | null {
  if (typeof containerSelector === "string") {
    return document.querySelector<HTMLCanvasElement>(containerSelector);
  }
  return containerSelector;
}

function renderChart(
  rawData: unknown,
  userQuery: string,
  containerSelector: string | HTMLCanvasElement,
  forcedChartType?: RenderChartType,
) {
  const canvas = resolveChartCanvas(containerSelector);
  if (!canvas) return null;

  cleanupChartCanvas(canvas);
  const normalized = normalizeChartData(rawData);
  const chartType = forcedChartType || selectChartType(normalized, userQuery || "");
  const chartData = prepareChartData(normalized, chartType);
  const ctx = canvas.getContext("2d");
  if (!ctx || !hasChartableData(chartData)) return null;

  applyDatasetColors(chartData.datasets, chartType, ctx, canvas, chartData.labels.length);

  const chartInstance = new Chart(ctx, {
    type: toChartJsType(chartType),
    data: {
      labels: chartData.labels,
      datasets: chartData.datasets as ChartDataset<ChartType, number[]>[],
    },
    options: buildChartOptions(chartType, chartData.labels.length),
    plugins: [depthShadowPlugin, threeDimensionalBarPlugin],
  } as ChartConfiguration<ChartType, number[], string>);

  const cursorHandler = (event: MouseEvent) => {
    const hits = chartInstance.getElementsAtEventForMode(event, "nearest", { intersect: true }, true);
    canvas.style.cursor = hits.length ? "crosshair" : "default";
  };
  canvas.addEventListener("mousemove", cursorHandler);
  chartCursorHandlers.set(canvas, cursorHandler);

  return chartInstance;
}

/* ─── Sub-renderers ─── */

function isScalarResult(rows: Array<Record<string, unknown>>): boolean {
  if (rows.length !== 1) return false;
  const cols = getUserFacingColumns(Object.keys(rows[0]));
  if (cols.length !== 1) return false;
  const val = rows[0][cols[0]];
  return typeof val === "string" || typeof val === "number" || val === null;
}

function renderScalarAnswerCard(rows: Array<Record<string, unknown>>, explanation?: string) {
  const cols = getUserFacingColumns(Object.keys(rows[0]));
  const col = cols[0];
  const value = rows[0][col];
  const displayValue = value === null || value === undefined ? "—" : String(value);
  const label = humanizeFieldName(col);

  return (
    <div className="viz-card scalar-answer-card">
      <div className="scalar-answer-inner">
        <div className="scalar-answer-icon">
          <Sparkles size={18} />
        </div>
        <div className="scalar-answer-body">
          <span className="scalar-answer-label">{label}</span>
          <span className="scalar-answer-value">{displayValue}</span>
          {explanation && <span className="scalar-answer-explanation">{explanation}</span>}
        </div>
      </div>
    </div>
  );
}

function renderTable(rows: Array<Record<string, unknown>>, title = "Data preview") {
  if (!rows.length) return null;
  const columns = getUserFacingColumns(Object.keys(rows[0]));
  return (
    <div className="viz-card">
      <h4>{title}</h4>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col}>{humanizeFieldName(col)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri}>
                {columns.map((col) => (
                  <td key={col}>{compactDisplayValue(row[col])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function QueryExplanation({ query }: { query?: string }) {
  return null;
}

function DataSageChart({
  rawData,
  userQuery,
  title,
  query,
  downloadName,
  preferredChartType,
  onSwitchView,
}: {
  rawData: unknown;
  userQuery: string;
  title: string;
  query?: string;
  downloadName: string;
  preferredChartType?: DataSageChartType | null;
  onSwitchView: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const normalized = normalizeChartData(rawData);
  const selectedChartType = resolveInitialChartType(normalized, userQuery, preferredChartType);
  const [viewOverride, setViewOverride] = useState<DataSageChartType | null>(null);
  const effectiveChartType = viewOverride || selectedChartType;
  const frameHeight = getChartFrameHeight(effectiveChartType, normalized.labels.length);

  useEffect(() => {
    setViewOverride(null);
  }, [rawData, userQuery]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;

    renderChart(rawData, userQuery, canvas, effectiveChartType);

    return () => {
      cleanupChartCanvas(canvas);
    };
  }, [rawData, userQuery, effectiveChartType]);

  const downloadChart = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const link = document.createElement("a");
    link.href = canvas.toDataURL("image/png");
    link.download = downloadName.toLowerCase().endsWith(".png") ? downloadName : `${downloadName}.png`;
    link.click();
  }, [downloadName]);

  const handleChartTypeChange = useCallback((event: React.ChangeEvent<HTMLSelectElement>) => {
    const nextChartType = event.target.value as DataSageChartType;
    setViewOverride(nextChartType === selectedChartType ? null : nextChartType);
  }, [selectedChartType]);

  if (!hasChartableData(normalized)) {
    return null;
  }

  return (
    <div className="viz-card chart-container">
      <div className="chart-header">
        <span className="chart-title">{title}</span>
        <div className="chart-actions">
          <label className="chart-select-shell">
            <span className="chart-select-caption">Visualization type</span>
            <select
              className="chart-select"
              value={effectiveChartType}
              onChange={handleChartTypeChange}
              aria-label="Select visualization type"
            >
              {CHART_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="chart-btn" onClick={onSwitchView}>
            <Layout size={14} />
            Switch view
          </button>
          <button type="button" className="chart-btn" onClick={downloadChart}>
            <Download size={14} />
            Download
          </button>
        </div>
      </div>
      <QueryExplanation query={query} />
      <div className="chart-canvas-wrap" style={{ height: frameHeight }}>
        <canvas ref={canvasRef} className="chart-canvas" aria-label={title} />
      </div>
    </div>
  );
}

/* ─── Main Visualization ─── */

function Visualization({ vizData, messageContent }: { vizData: string; messageContent?: string }) {
  const [viewMode, setViewMode] = useState<"chart" | "table">("chart");

  useEffect(() => {
    setViewMode("chart");
  }, [vizData]);

  try {
    const parsed = JSON.parse(vizData) as VizPayload;
    const rows = Array.isArray(parsed.rows) ? parsed.rows.filter(isRecord) : [];
    const traces = Array.isArray(parsed.viz_spec?.data)
      ? parsed.viz_spec!.data!.filter((trace): trace is PlotlyTrace => isRecord(trace))
      : [];
    const title = prettifyTitle(readTitle(parsed.viz_spec?.layout?.title) ?? "Visualization");
    const explanation = parsed.explanation ?? undefined;
    const query = typeof parsed.query === "string" ? parsed.query : undefined;
    const imageSource =
      parsed.viz_image && parsed.viz_mime ? `data:${parsed.viz_mime};base64,${parsed.viz_image}` : null;
    const downloadName = parsed.viz_filename ?? "visualization.png";

    if (isScalarResult(rows) && !traces.length && !imageSource) {
      return renderScalarAnswerCard(rows, explanation ?? query);
    }

    const rawChartData = pickBestRawChartData(rows, traces);
    const chartIntent = [title, explanation, parsed.chart_type, query, messageContent].filter(Boolean).join(" ");

    if (rawChartData && hasChartableData(normalizeChartData(rawChartData))) {
      if (viewMode === "table") {
        const tableRows = Array.isArray(rawChartData) ? rawChartData.filter(isRecord) : [];
        const columns = tableRows.length > 0 ? getUserFacingColumns(Object.keys(tableRows[0])) : [];
        return (
          <div className="viz-card">
            <div className="chart-header">
              <span className="chart-title">{title || "Data preview"}</span>
              <div className="chart-actions">
                <button type="button" className="chart-btn" onClick={() => setViewMode("chart")}>
                  <Layout size={14} />
                  Switch view
                </button>
              </div>
            </div>
            {tableRows.length > 0 && (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      {columns.map((col) => (
                        <th key={col}>{humanizeFieldName(col)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tableRows.map((row, ri) => (
                      <tr key={ri}>
                        {columns.map((col) => (
                          <td key={col}>{compactDisplayValue(row[col])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );
      }

      return (
        <DataSageChart
          rawData={rawChartData}
          userQuery={chartIntent}
          title={title}
          query={query}
          downloadName={downloadName}
          preferredChartType={mapPreferredChartType(parsed.chart_type)}
          onSwitchView={() => setViewMode("table")}
        />
      );
    }

    if (imageSource) {
      return (
        <div className="viz-card viz-image-card">
          <div className="viz-image-header">
            <h4>{title}</h4>
            <a className="viz-download-button" href={imageSource} download={downloadName}>
              <Download size={16} />
              Download
            </a>
          </div>
          <QueryExplanation query={query} />
          <div className="viz-image-frame">
            <img src={imageSource} alt={title} className="viz-image" />
          </div>
        </div>
      );
    }

    if (isScalarResult(rows)) return renderScalarAnswerCard(rows, explanation ?? query);
    return renderTable(rows);
  } catch {
    return null;
  }
}

const MemoizedVisualization = React.memo(
  Visualization,
  (prev, next) => prev.vizData === next.vizData && prev.messageContent === next.messageContent,
);

/* ─── ChatMessage ─── */

function ChatMessage({
  message,
  userDisplayName,
  onFollowUpClick,
}: {
  message: Message;
  userDisplayName?: string;
  onFollowUpClick?: (text: string) => void;
}) {
  const isUser = message.role === "user";
  const isStreaming = !isUser && message.status === "streaming";
  const showStreamLoader = isStreaming && !message.content.trim();
  const resolvedUserDisplayName = userDisplayName?.trim() || "You";
  const streamingStatusLabel = message.stage_label?.trim() || "Generating insight";

  return (
    <article className={`message-card ${isUser ? "user" : "assistant"}`}>
      <div className="message-meta">
        <span className="message-avatar">
          {isUser ? (
            userDisplayName?.trim() ? (
              <span className="message-avatar-initials">{getNameInitials(resolvedUserDisplayName)}</span>
            ) : (
              <User size={20} />
            )
          ) : (
            <BrandLogoIcon size={20} />
          )}
        </span>
        <div>
          <span className="message-role">{isUser ? resolvedUserDisplayName : "DataSage AI"}</span>
          <span className="message-time">
            {isUser ? "Prompt sent" : isStreaming ? streamingStatusLabel : "Insight generated"}
          </span>
        </div>
      </div>

      {showStreamLoader ? (
        <div className="assistant-stream-chip premium-loader" aria-live="polite">
          <div className="viz-loader-bars" aria-hidden="true">
            <div className="viz-bar"></div>
            <div className="viz-bar"></div>
            <div className="viz-bar"></div>
            <div className="viz-bar"></div>
          </div>
          <span className="premium-loader-text">{streamingStatusLabel}...</span>
        </div>
      ) : null}

      {isStreaming ? (
        <StreamingMessageContent content={message.content} />
      ) : (
        <div className="message-content">{renderMessageContent(message.content)}</div>
      )}
      {message.viz_data ? <MemoizedVisualization vizData={message.viz_data} messageContent={message.content} /> : null}

      {/* ── Anomaly Alert ── */}
      {!message.role.startsWith("u") && message.anomaly_data?.has_anomalies ? (
        <div className="anomaly-alert">
          <span className="anomaly-alert-icon">⚠</span>
          <div>
            <strong>Anomaly Detected</strong>
            <p style={{ margin: "4px 0 6px" }}>{message.anomaly_data.summary}</p>
            <div className="anomaly-list">
              {message.anomaly_data.anomalies.slice(0, 4).map((a, i) => (
                <span key={i} className="anomaly-pill">
                  {a.field}: <strong>{typeof a.value === "number" ? a.value.toLocaleString() : a.value}</strong>
                  {a.zscore > 0 ? ` (z=${a.zscore})` : ""}
                </span>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      {/* ── Forecast Summary ── */}
      {!message.role.startsWith("u") && message.forecast_data?.forecast?.length ? (
        <div className="forecast-card">
          <div className="forecast-header">
            <span className="forecast-badge">🔮 Forecast</span>
            <span className="forecast-method">{message.forecast_data.method}</span>
          </div>
          <p className="forecast-summary">{message.forecast_data.summary}</p>
          <div className="forecast-values">
            {message.forecast_data.forecast.slice(0, 5).map((v, i) => (
              <span key={i} className="forecast-value-chip">
                {message.forecast_data!.ts_labels.length > 0
                  ? `+${i + 1}`
                  : `Period ${i + 1}`}: <strong>{typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : v}</strong>
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {/* ── Follow-up Chips ── */}
      {!message.role.startsWith("u") && message.status === "complete" && message.follow_ups && message.follow_ups.length > 0 ? (
        <div className="follow-up-chips">
          {message.follow_ups.map((suggestion, i) => (
            <button
              key={i}
              type="button"
              className="follow-up-chip"
              onClick={() => onFollowUpClick?.(suggestion)}
            >
              {suggestion}
            </button>
          ))}
        </div>
      ) : null}
    </article>
  );
}

export default React.memo(
  ChatMessage,
  (prev, next) =>
    prev.message.role === next.message.role &&
    prev.message.content === next.message.content &&
    prev.message.viz_data === next.message.viz_data &&
    prev.message.status === next.message.status &&
    prev.userDisplayName === next.userDisplayName &&
    prev.onFollowUpClick === next.onFollowUpClick,
);
