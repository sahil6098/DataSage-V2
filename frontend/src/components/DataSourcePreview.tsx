"use client";

import { useEffect, useState } from "react";
import {
  BarChart3,
  Database,
  FileSpreadsheet,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import api from "@/lib/api";

const PREVIEW_ROW_LIMIT = 200;
const MAX_CHART_ITEMS = 14;
const CHART_COLORS = ["#2563eb", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"];
const numberFormatter = new Intl.NumberFormat("en-US");
const dateFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
});

export interface ConnectedSourceConfig {
  type?: string;
  file_name?: string | null;
  database_name?: string | null;
  connection_uri?: string | null;
  selected_tables?: string[];
  database_description?: string | null;
  table_descriptions?: Record<string, string>;
  field_descriptions?: Record<string, Record<string, string>>;
}

interface PreviewField {
  name: string;
  type?: string;
  nullable?: boolean;
  samples?: string[];
  description?: string | null;
}

interface PreviewTable {
  name: string;
  row_count?: number | null;
  fields?: PreviewField[];
  selected?: boolean;
  description?: string | null;
}

interface SchemaResponse {
  source_type?: string;
  database_name?: string | null;
  database_description?: string | null;
  selected_table_count?: number;
  tables?: PreviewTable[];
}

interface SchemaContextDraft {
  selectedTables: string[];
  databaseDescription: string;
  tableDescriptions: Record<string, string>;
  fieldDescriptions: Record<string, Record<string, string>>;
}

interface PreviewChartPoint {
  label: string;
  fullLabel: string;
  value: number;
}

interface PreviewChartModel {
  kind: "horizontal-bar" | "vertical-bar" | "line";
  title: string;
  description: string;
  xAxisLabel: string;
  yAxisLabel: string;
  data: PreviewChartPoint[];
}

interface DataSourcePreviewProps {
  sessionId: string;
  sourceConfig: ConnectedSourceConfig | null;
  refreshToken: number;
  isOpen: boolean;
  onClose: () => void;
  onConnectionStateChange?: (isActive: boolean) => void;
}

function buildSchemaContextDraft(schema: SchemaResponse | null): SchemaContextDraft {
  const tables = Array.isArray(schema?.tables) ? schema.tables : [];

  return {
    selectedTables: tables.filter((table) => table.selected ?? true).map((table) => table.name),
    databaseDescription: schema?.database_description || "",
    tableDescriptions: Object.fromEntries(
      tables
        .filter((table) => Boolean(table.description))
        .map((table) => [table.name, table.description?.trim() || ""]),
    ),
    fieldDescriptions: Object.fromEntries(
      tables
        .map((table) => {
          const describedFields = Object.fromEntries(
            (table.fields || [])
              .filter((field) => Boolean(field.description))
              .map((field) => [field.name, field.description?.trim() || ""]),
          );
          return [table.name, describedFields];
        })
        .filter((entry) => Object.keys(entry[1]).length > 0),
    ),
  };
}

function compactDescriptionMap(values: Record<string, string>) {
  return Object.fromEntries(
    Object.entries(values)
      .map(([key, value]) => [key, value.trim()])
      .filter((entry) => Boolean(entry[1])),
  );
}

function compactFieldDescriptionMap(values: Record<string, Record<string, string>>) {
  return Object.fromEntries(
    Object.entries(values)
      .map(([tableName, fieldMap]) => [tableName, compactDescriptionMap(fieldMap)])
      .filter((entry) => Object.keys(entry[1]).length > 0),
  );
}

function formatSourceLabel(sourceConfig: ConnectedSourceConfig | null, schema: SchemaResponse | null) {
  return (
    sourceConfig?.file_name ||
    schema?.database_name ||
    sourceConfig?.database_name ||
    schema?.tables?.[0]?.name ||
    "Connected source"
  );
}

function describeSource(sourceType?: string) {
  switch ((sourceType || "").toLowerCase()) {
    case "csv":
      return "CSV preview";
    case "excel":
      return "Spreadsheet preview";
    case "mongodb":
      return "MongoDB preview";
    case "postgresql":
      return "PostgreSQL preview";
    case "mysql":
      return "MySQL preview";
    default:
      return "Data preview";
  }
}

function formatColumnLabel(value: string) {
  const normalized = value.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "Column";
  }

  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function isIdentifierField(value: string) {
  const normalized = value.trim().toLowerCase();
  return normalized === "id" || normalized === "_id" || normalized === "unnamed: 0" || normalized.endsWith("_id") || normalized.startsWith("id_");
}

function getPreviewColumns(columns: string[]) {
  const withoutIndex = columns.filter((column) => column.trim().toLowerCase() !== "unnamed: 0");
  const withoutIdentifiers = withoutIndex.filter((column) => !isIdentifierField(column));
  return withoutIdentifiers.length ? withoutIdentifiers : withoutIndex;
}

function shortenLabel(value: string, maxLength = 28) {
  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength - 3)}...`;
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string" && value.trim()) {
    const numericValue = Number(value);
    if (Number.isFinite(numericValue)) {
      return numericValue;
    }
  }

  return null;
}

function parseDateValue(value: unknown): Date | null {
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return value;
  }

  if (typeof value !== "string") {
    return null;
  }

  const trimmedValue = value.trim();
  if (!trimmedValue || !/[-/:T]/.test(trimmedValue)) {
    return null;
  }

  const parsedTimestamp = Date.parse(trimmedValue);
  if (Number.isNaN(parsedTimestamp)) {
    return null;
  }

  return new Date(parsedTimestamp);
}

function isNumericField(field?: PreviewField) {
  const type = (field?.type || "").toLowerCase();
  return ["int", "float", "double", "decimal", "numeric", "real", "number"].some((token) => type.includes(token));
}

function isDateField(field?: PreviewField) {
  const type = (field?.type || "").toLowerCase();
  return ["date", "time"].some((token) => type.includes(token));
}

function readCategoryLabel(value: unknown, index: number) {
  if (value === null || value === undefined) {
    return `Blank ${index + 1}`;
  }

  const normalizedValue = String(value).trim();
  return normalizedValue || `Blank ${index + 1}`;
}

function buildCategoryCountChart(rows: Array<Record<string, unknown>>, categoryColumn: string): PreviewChartModel | null {
  const counts = new Map<string, number>();

  rows.forEach((row, rowIndex) => {
    const label = readCategoryLabel(row[categoryColumn], rowIndex);
    counts.set(label, (counts.get(label) || 0) + 1);
  });

  const data = Array.from(counts.entries())
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, MAX_CHART_ITEMS)
    .map(([fullLabel, value]) => ({
      label: shortenLabel(fullLabel, 30),
      fullLabel,
      value,
    }));

  if (data.length < 2) {
    return null;
  }

  const columnLabel = formatColumnLabel(categoryColumn);
  return {
    kind: "horizontal-bar",
    title: `${columnLabel} Distribution by Count`,
    description: `Top ${data.length} values ranked from the preview sample.`,
    xAxisLabel: "Count",
    yAxisLabel: columnLabel,
    data,
  };
}

function buildCategoryMetricChart(
  rows: Array<Record<string, unknown>>,
  categoryColumn: string,
  valueColumn: string,
): PreviewChartModel | null {
  const values = new Map<string, number>();

  rows.forEach((row, rowIndex) => {
    const numericValue = toNumber(row[valueColumn]);
    if (numericValue === null) {
      return;
    }

    const label = readCategoryLabel(row[categoryColumn], rowIndex);
    values.set(label, (values.get(label) || 0) + numericValue);
  });

  const data = Array.from(values.entries())
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, MAX_CHART_ITEMS)
    .map(([fullLabel, value]) => ({
      label: shortenLabel(fullLabel, 30),
      fullLabel,
      value,
    }));

  if (data.length < 2) {
    return null;
  }

  const categoryLabel = formatColumnLabel(categoryColumn);
  const valueLabel = formatColumnLabel(valueColumn);
  return {
    kind: "horizontal-bar",
    title: `${valueLabel} by ${categoryLabel}`,
    description: `Aggregated totals from the preview sample.`,
    xAxisLabel: valueLabel,
    yAxisLabel: categoryLabel,
    data,
  };
}

function buildTimeSeriesChart(
  rows: Array<Record<string, unknown>>,
  dateColumn: string,
  valueColumn: string,
): PreviewChartModel | null {
  const data = rows
    .map((row) => {
      const dateValue = parseDateValue(row[dateColumn]);
      const numericValue = toNumber(row[valueColumn]);

      if (!dateValue || numericValue === null) {
        return null;
      }

      return {
        fullLabel: dateFormatter.format(dateValue),
        label: dateFormatter.format(dateValue),
        value: numericValue,
        timestamp: dateValue.getTime(),
      };
    })
    .filter(
      (point): point is PreviewChartPoint & { timestamp: number } =>
        point !== null && Number.isFinite(point.timestamp),
    )
    .sort((left, right) => left.timestamp - right.timestamp)
    .slice(-Math.max(10, Math.min(rows.length, 24)))
    .map(({ timestamp: _timestamp, ...point }) => point);

  if (data.length < 2) {
    return null;
  }

  const dateLabel = formatColumnLabel(dateColumn);
  const valueLabel = formatColumnLabel(valueColumn);
  return {
    kind: "line",
    title: `${valueLabel} Over Time`,
    description: `Chronological trend built from the preview sample.`,
    xAxisLabel: dateLabel,
    yAxisLabel: valueLabel,
    data,
  };
}

function buildNumericDistributionChart(
  rows: Array<Record<string, unknown>>,
  numericColumn: string,
): PreviewChartModel | null {
  const numericValues = rows
    .map((row) => toNumber(row[numericColumn]))
    .filter((value): value is number => value !== null);

  if (numericValues.length < 3) {
    return null;
  }

  const minValue = Math.min(...numericValues);
  const maxValue = Math.max(...numericValues);

  if (minValue === maxValue) {
    return {
      kind: "vertical-bar",
      title: `${formatColumnLabel(numericColumn)} Distribution`,
      description: "Every preview row falls into the same numeric value.",
      xAxisLabel: formatColumnLabel(numericColumn),
      yAxisLabel: "Count",
      data: [
        {
          label: String(minValue),
          fullLabel: String(minValue),
          value: numericValues.length,
        },
      ],
    };
  }

  const bucketCount = Math.max(6, Math.min(10, Math.ceil(Math.sqrt(numericValues.length))));
  const bucketSize = (maxValue - minValue) / bucketCount;
  const buckets = Array.from({ length: bucketCount }, (_value, index) => {
    const start = minValue + bucketSize * index;
    const end = minValue + bucketSize * (index + 1);
    return {
      start,
      end,
      label: `${start.toFixed(1)}-${end.toFixed(1)}`,
      fullLabel: `${start.toFixed(2)} to ${end.toFixed(2)}`,
      value: 0,
    };
  });

  numericValues.forEach((value) => {
    const bucketIndex = Math.min(bucketCount - 1, Math.floor((value - minValue) / bucketSize));
    buckets[bucketIndex].value += 1;
  });

  const data = buckets.filter((bucket) => bucket.value > 0).map(({ start: _start, end: _end, ...bucket }) => bucket);
  if (data.length < 2) {
    return null;
  }

  const numericLabel = formatColumnLabel(numericColumn);
  return {
    kind: "vertical-bar",
    title: `${numericLabel} Distribution`,
    description: "Grouped into buckets from the preview sample.",
    xAxisLabel: numericLabel,
    yAxisLabel: "Count",
    data,
  };
}

function buildPreviewChart(rows: Array<Record<string, unknown>>, fields: PreviewField[]): PreviewChartModel | null {
  if (!rows.length) {
    return null;
  }

  const columns = getPreviewColumns(fields.length ? fields.map((field) => field.name) : Object.keys(rows[0]));
  const fieldMap = new Map(fields.map((field) => [field.name, field]));
  const numericColumns = columns.filter(
    (column) => isNumericField(fieldMap.get(column)) || rows.some((row) => toNumber(row[column]) !== null),
  );
  const dateColumns = columns.filter(
    (column) => isDateField(fieldMap.get(column)) || rows.some((row) => parseDateValue(row[column]) !== null),
  );
  const categoricalColumns = columns.filter((column) =>
    rows.some((row, index) => {
      const value = row[column];
      if (value === null || value === undefined || readCategoryLabel(value, index).startsWith("Blank ")) {
        return false;
      }
      return toNumber(value) === null;
    }),
  );

  for (const dateColumn of dateColumns) {
    for (const numericColumn of numericColumns) {
      if (dateColumn === numericColumn) {
        continue;
      }

      const chart = buildTimeSeriesChart(rows, dateColumn, numericColumn);
      if (chart) {
        return chart;
      }
    }
  }

  for (const categoryColumn of categoricalColumns) {
    const numericColumn = numericColumns.find((column) => column !== categoryColumn);
    if (!numericColumn) {
      continue;
    }

    const chart = buildCategoryMetricChart(rows, categoryColumn, numericColumn);
    if (chart) {
      return chart;
    }
  }

  for (const categoryColumn of categoricalColumns) {
    const chart = buildCategoryCountChart(rows, categoryColumn);
    if (chart) {
      return chart;
    }
  }

  const fallbackNumericColumn = numericColumns.find((column) => !dateColumns.includes(column));
  if (fallbackNumericColumn) {
    return buildNumericDistributionChart(rows, fallbackNumericColumn);
  }

  return null;
}

function getChartHeight(chartModel: PreviewChartModel) {
  if (chartModel.kind === "horizontal-bar") {
    return Math.min(760, Math.max(360, chartModel.data.length * 42 + 86));
  }

  return 340;
}

function formatFieldSamples(field: PreviewField) {
  if (!Array.isArray(field.samples) || field.samples.length === 0) {
    return "Samples show after preview loads";
  }

  return field.samples.slice(0, 2).join(" | ");
}

export default function DataSourcePreview({
  sessionId,
  sourceConfig,
  refreshToken,
  isOpen,
  onClose,
  onConnectionStateChange,
}: DataSourcePreviewProps) {
  const [schema, setSchema] = useState<SchemaResponse | null>(null);
  const [selectedTable, setSelectedTable] = useState("");
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([]);
  const [loadingSchema, setLoadingSchema] = useState(false);
  const [loadingRows, setLoadingRows] = useState(false);
  const [savingContext, setSavingContext] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [schemaContextDraft, setSchemaContextDraft] = useState<SchemaContextDraft>({
    selectedTables: [],
    databaseDescription: "",
    tableDescriptions: {},
    fieldDescriptions: {},
  });
  const [schemaContextStatus, setSchemaContextStatus] = useState<{ tone: "success" | "error"; message: string } | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [qualityReport, setQualityReport] = useState<Record<string, {
    quality_score: number;
    quality_label: string;
    duplicate_rows: number;
    duplicate_pct: number;
    avg_missing_pct: number;
    outlier_columns: string[];
    missing_by_column: Record<string, { count: number; pct: number }>;
  }> | null>(null);
  const [loadingQuality, setLoadingQuality] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    if (!sessionId || !sourceConfig) {
      setSchema(null);
      setRows([]);
      setSelectedTable("");
      setError(null);
      setSchemaContextDraft({
        selectedTables: [],
        databaseDescription: "",
        tableDescriptions: {},
        fieldDescriptions: {},
      });
      setSchemaContextStatus(null);
      return;
    }

    let cancelled = false;

    const fetchSchema = async () => {
      setLoadingSchema(true);
      setError(null);

      try {
        const response = await api.get(`/connectors/${sessionId}/schema`);
        const nextSchema = (response.data.data || {}) as SchemaResponse;
        const nextTables = Array.isArray(nextSchema.tables) ? nextSchema.tables : [];

        if (cancelled) {
          return;
        }

        setSchema(nextSchema);
        setSchemaContextDraft(buildSchemaContextDraft(nextSchema));
        setSchemaContextStatus(null);
        setSelectedTable((currentTable) => {
          if (currentTable && nextTables.some((table) => table.name === currentTable)) {
            return currentTable;
          }
          return nextTables[0]?.name || "";
        });
        onConnectionStateChange?.(true);

        // Fetch Quality Report in parallel
        try {
          const qRes = await api.get(`/connectors/${sessionId}/quality`);
          if (qRes.data?.data) {
            setQualityReport(qRes.data.data);
          } else {
            setQualityReport(null);
          }
        } catch (qErr) {
          console.error("Quality report fetch failed:", qErr);
          setQualityReport(null);
        }
      } catch (fetchError: unknown) {
        if (cancelled) {
          return;
        }

        const message = (
          typeof fetchError === "object" &&
          fetchError &&
          "response" in fetchError &&
          typeof (fetchError as { response?: { data?: { message?: string } } }).response?.data?.message === "string"
            ? (fetchError as { response?: { data?: { message?: string } } }).response?.data?.message
            : undefined
        ) || "Preview is unavailable right now. Reconnect the source to load schema details.";

        setSchema(null);
        setRows([]);
        setSelectedTable("");
        setError(message);
        setSchemaContextStatus(null);
        onConnectionStateChange?.(false);
      } finally {
        if (!cancelled) {
          setLoadingSchema(false);
        }
      }
    };

    void fetchSchema();

    return () => {
      cancelled = true;
    };
  }, [isOpen, sessionId, sourceConfig, refreshToken, reloadNonce, onConnectionStateChange]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    if (!sessionId || !selectedTable || !sourceConfig) {
      setRows([]);
      return;
    }

    let cancelled = false;

    const fetchRows = async () => {
      setLoadingRows(true);

      try {
        const response = await api.get(`/connectors/${sessionId}/preview/${encodeURIComponent(selectedTable)}`, {
          params: { limit: PREVIEW_ROW_LIMIT },
        });

        if (cancelled) {
          return;
        }

        setRows(Array.isArray(response.data.data?.rows) ? response.data.data.rows : []);
        setError(null);
        onConnectionStateChange?.(true);
      } catch (fetchError: unknown) {
        if (cancelled) {
          return;
        }

        const message = (
          typeof fetchError === "object" &&
          fetchError &&
          "response" in fetchError &&
          typeof (fetchError as { response?: { data?: { message?: string } } }).response?.data?.message === "string"
            ? (fetchError as { response?: { data?: { message?: string } } }).response?.data?.message
            : undefined
        ) || "Could not load preview rows for the selected table.";

        setRows([]);
        setError(message);
        onConnectionStateChange?.(false);
      } finally {
        if (!cancelled) {
          setLoadingRows(false);
        }
      }
    };

    void fetchRows();

    return () => {
      cancelled = true;
    };
  }, [isOpen, sessionId, selectedTable, sourceConfig, onConnectionStateChange]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  const handleTableSelectionToggle = (tableName: string) => {
    setSchemaContextStatus(null);
    setSchemaContextDraft((currentDraft) => {
      const nextSelectedTables = currentDraft.selectedTables.includes(tableName)
        ? currentDraft.selectedTables.filter((value) => value !== tableName)
        : [...currentDraft.selectedTables, tableName];

      return {
        ...currentDraft,
        selectedTables: nextSelectedTables,
      };
    });
  };

  const handleDatabaseDescriptionChange = (value: string) => {
    setSchemaContextStatus(null);
    setSchemaContextDraft((currentDraft) => ({
      ...currentDraft,
      databaseDescription: value,
    }));
  };

  const handleTableDescriptionChange = (tableName: string, value: string) => {
    setSchemaContextStatus(null);
    setSchemaContextDraft((currentDraft) => ({
      ...currentDraft,
      tableDescriptions: {
        ...currentDraft.tableDescriptions,
        [tableName]: value,
      },
    }));
  };

  const handleFieldDescriptionChange = (tableName: string, fieldName: string, value: string) => {
    setSchemaContextStatus(null);
    setSchemaContextDraft((currentDraft) => ({
      ...currentDraft,
      fieldDescriptions: {
        ...currentDraft.fieldDescriptions,
        [tableName]: {
          ...(currentDraft.fieldDescriptions[tableName] || {}),
          [fieldName]: value,
        },
      },
    }));
  };

  const handleSaveSchemaContext = async () => {
    if (!sessionId) {
      return;
    }

    const selectedTables = schemaContextDraft.selectedTables.filter(Boolean);

    setSavingContext(true);
    setSchemaContextStatus(null);

    try {
      const response = await api.patch(`/connectors/${sessionId}/schema-context`, {
        selected_tables: selectedTables,
        database_description: schemaContextDraft.databaseDescription.trim() || null,
        table_descriptions: compactDescriptionMap(schemaContextDraft.tableDescriptions),
        field_descriptions: compactFieldDescriptionMap(schemaContextDraft.fieldDescriptions),
      });

      const nextSchema = (response.data.data || {}) as SchemaResponse;
      const nextTables = Array.isArray(nextSchema.tables) ? nextSchema.tables : [];

      setSchema(nextSchema);
      setSchemaContextDraft(buildSchemaContextDraft(nextSchema));
      setSchemaContextStatus({
        tone: "success",
        message: selectedTables.length
          ? "Bot guidance saved. Future answers will use the selected tables and descriptions."
          : "Bot guidance saved. No tables are selected, so data questions will wait for a table selection.",
      });
      setSelectedTable((currentTable) => {
        if (currentTable && nextTables.some((table) => table.name === currentTable)) {
          return currentTable;
        }
        return nextTables[0]?.name || "";
      });
      onConnectionStateChange?.(true);
    } catch (saveError: unknown) {
      const message = (
        typeof saveError === "object" &&
        saveError &&
        "response" in saveError &&
        typeof (saveError as { response?: { data?: { message?: string } } }).response?.data?.message === "string"
          ? (saveError as { response?: { data?: { message?: string } } }).response?.data?.message
          : undefined
      ) || "Could not save the schema context for this source.";

      setSchemaContextStatus({ tone: "error", message });
    } finally {
      setSavingContext(false);
    }
  };

  const tables = Array.isArray(schema?.tables) ? schema.tables : [];
  const selectedTableMeta = tables.find((table) => table.name === selectedTable) || tables[0] || null;
  const columns = getPreviewColumns(rows.length
    ? Object.keys(rows[0])
    : Array.isArray(selectedTableMeta?.fields)
      ? selectedTableMeta.fields.map((field) => field.name)
      : []);
  const sourceType = schema?.source_type || sourceConfig?.type || "data";
  const sourceLabel = formatSourceLabel(sourceConfig, schema);
  const isLoading = loadingSchema || loadingRows;
  const totalRowCount = selectedTableMeta?.row_count ?? rows.length ?? 0;
  const previewFields = (selectedTableMeta?.fields || []).filter((field) => !isIdentifierField(field.name));
  const fieldCount = previewFields.length || columns.length;
  const chartModel = buildPreviewChart(rows, selectedTableMeta?.fields || []);
  const hasChart = Boolean(chartModel && chartModel.data.length);
  const [chartReady, setChartReady] = useState(false);
  const previewSampleLabel =
    totalRowCount > rows.length
      ? `Using the first ${numberFormatter.format(rows.length)} preview rows of ${numberFormatter.format(totalRowCount)} total rows.`
      : `Using ${numberFormatter.format(rows.length)} preview rows.`;
  const visibleFields = previewFields.slice(0, 6);
  const hiddenFieldCount = Math.max(0, previewFields.length - visibleFields.length);
  const selectedTablesForContext = schemaContextDraft.selectedTables;
  const selectedTableCount = selectedTablesForContext.length;
  const currentTableDescription = selectedTableMeta ? (schemaContextDraft.tableDescriptions[selectedTableMeta.name] || "") : "";
  const currentFieldDescriptions = selectedTableMeta ? (schemaContextDraft.fieldDescriptions[selectedTableMeta.name] || {}) : {};
  const databaseDescriptionLength = schemaContextDraft.databaseDescription.trim().length;

  useEffect(() => {
    if (!isOpen || !hasChart) {
      setChartReady(false);
      return;
    }

    setChartReady(false);
    const frame = window.requestAnimationFrame(() => setChartReady(true));
    return () => window.cancelAnimationFrame(frame);
  }, [isOpen, hasChart, selectedTable, rows.length]);

  if (!sourceConfig) {
    return null;
  }

  const renderChart = () => {
    if (!chartModel) {
      return null;
    }

    return (
      <div className="preview-chart-card">
        <div className="preview-chart-header">
          <div>
            <h4>{chartModel.title}</h4>
            <p>{chartModel.description}</p>
          </div>
          <span className="preview-chart-pill">
            <BarChart3 size={16} />
            Graph
          </span>
        </div>

        <div className="preview-chart-frame" style={{ height: getChartHeight(chartModel) }}>
          {chartReady ? (
            <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1} debounce={80}>
              {chartModel.kind === "line" ? (
                <LineChart data={chartModel.data} margin={{ top: 12, right: 12, left: -18, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#dbe4f0" />
                  <XAxis
                    dataKey="label"
                    tick={{ fill: "#60708a", fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                    minTickGap={18}
                  />
                  <YAxis
                    tick={{ fill: "#60708a", fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                    label={{ value: chartModel.yAxisLabel, angle: -90, position: "insideLeft", fill: "#60708a" }}
                  />
                  <Tooltip
                    formatter={(value) => numberFormatter.format(Number(value ?? 0))}
                    labelFormatter={(label, payload) => String(payload?.[0]?.payload?.fullLabel || label)}
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke={CHART_COLORS[0]}
                    strokeWidth={3}
                    dot={{ fill: CHART_COLORS[0], strokeWidth: 0, r: 4 }}
                    activeDot={{ r: 6 }}
                  />
                </LineChart>
              ) : chartModel.kind === "vertical-bar" ? (
                <BarChart data={chartModel.data} margin={{ top: 12, right: 12, left: -18, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#dbe4f0" />
                  <XAxis
                    dataKey="label"
                    tick={{ fill: "#60708a", fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                    minTickGap={12}
                  />
                  <YAxis
                    tick={{ fill: "#60708a", fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                    label={{ value: chartModel.yAxisLabel, angle: -90, position: "insideLeft", fill: "#60708a" }}
                  />
                  <Tooltip
                    formatter={(value) => numberFormatter.format(Number(value ?? 0))}
                    labelFormatter={(label, payload) => String(payload?.[0]?.payload?.fullLabel || label)}
                  />
                  <Bar dataKey="value" radius={[12, 12, 0, 0]}>
                    {chartModel.data.map((point, index) => (
                      <Cell key={point.fullLabel} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              ) : (
                <BarChart data={chartModel.data} layout="vertical" margin={{ top: 12, right: 12, left: 36, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#dbe4f0" />
                  <XAxis
                    type="number"
                    tick={{ fill: "#60708a", fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                    label={{ value: chartModel.xAxisLabel, position: "insideBottom", offset: -4, fill: "#60708a" }}
                  />
                  <YAxis
                    type="category"
                    dataKey="label"
                    width={176}
                    tick={{ fill: "#60708a", fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    formatter={(value) => numberFormatter.format(Number(value ?? 0))}
                    labelFormatter={(label, payload) => String(payload?.[0]?.payload?.fullLabel || label)}
                  />
                  <Bar dataKey="value" radius={[0, 12, 12, 0]}>
                    {chartModel.data.map((point, index) => (
                      <Cell key={point.fullLabel} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              )}
            </ResponsiveContainer>
          ) : null}
        </div>

        <p className="preview-chart-note">{previewSampleLabel}</p>
      </div>
    );
  };

  return (
    <>
      <button
        type="button"
        className={`data-preview-backdrop ${isOpen ? "open" : ""}`}
        onClick={onClose}
        aria-hidden={!isOpen}
        tabIndex={isOpen ? 0 : -1}
      />

      <aside
        className={`data-preview-panel ${isOpen ? "open" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-hidden={!isOpen}
        aria-label={`${sourceLabel} preview`}
      >
        <div className="data-preview-head">
          <div>
            <div className="brand-row preview-badge">
              <span className="brand-mark">
                {sourceType === "csv" || sourceType === "excel" ? <FileSpreadsheet size={16} /> : <Database size={16} />}
              </span>
              {describeSource(sourceType)}
            </div>
            <h3>{sourceLabel}</h3>
            <p className="helper-text">
              {selectedTableMeta
                ? `${numberFormatter.format(totalRowCount)} rows in ${selectedTableMeta.name}`
                : "Connected source overview"}
            </p>
          </div>

          <div className="preview-header-actions">
            <button
              type="button"
              className="btn-ghost preview-refresh"
              onClick={() => {
                setReloadNonce((currentValue) => currentValue + 1);
              }}
              aria-label="Refresh preview"
            >
              <RefreshCw size={18} />
            </button>
            <button type="button" className="btn-ghost preview-close" onClick={onClose} aria-label="Close preview">
              <span aria-hidden="true">✕</span>
            </button>
          </div>
        </div>

        <div className="data-preview-scroll">
          {tables.length > 1 ? (
            <div className="preview-toolbar">
              <label className="preview-toolbar-label" htmlFor="preview-table-select">
                Table
              </label>
              <select
                id="preview-table-select"
                className="preview-select"
                value={selectedTable}
                onChange={(event) => setSelectedTable(event.target.value)}
              >
                {tables.map((table) => (
                  <option key={table.name} value={table.name}>
                    {table.name}
                  </option>
                ))}
              </select>
            </div>
          ) : null}

          {error ? (
            <div className="info-banner preview-message">
              <Database size={18} />
              {error}
            </div>
          ) : null}

          {isLoading ? (
            <div className="loading-shell preview-loading">
              <div className="loading-line short" />
              <div className="loading-line medium" />
              <div className="loading-line" />
            </div>
          ) : columns.length ? (
            <>
              <div className="preview-summary-grid">
                <article className="preview-summary-card">
                  <span>Total rows</span>
                  <strong>{numberFormatter.format(totalRowCount)}</strong>
                  <small>Detected from schema</small>
                </article>
                <article className="preview-summary-card">
                  <span>Columns</span>
                  <strong>{numberFormatter.format(fieldCount)}</strong>
                  <small>Available in this source</small>
                </article>
                <article className="preview-summary-card">
                  <span>Best view</span>
                  <strong>{hasChart ? "Graph" : "Rows"}</strong>
                  <small>{hasChart ? "Auto-picked from the preview" : "No chartable pattern detected yet"}</small>
                </article>
              </div>
 
              {/* ── Data Quality Assessment Card ── */}
              {qualityReport && selectedTable && qualityReport[selectedTable] ? (() => {
                const report = qualityReport[selectedTable];
                return (
                  <section className="schema-context-card" style={{ marginTop: 20 }}>
                    <div className="schema-context-header" style={{ borderBottom: "1px solid rgba(255,255,255,0.06)", paddingBottom: 12 }}>
                      <div>
                        <h4 style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <Sparkles size={16} style={{ color: "#818cf8" }} />
                          Data Quality Assessment
                        </h4>
                        <p style={{ margin: "4px 0 0" }}>Analysis sample stats to identify gaps, duplicates, or missing metrics.</p>
                      </div>
                      <span className={`status-pill ${report.quality_score >= 85 ? "success" : report.quality_score >= 65 ? "info" : "warning"}`} style={{ fontSize: 13, background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.3)", color: "#a5b4fc" }}>
                        Score: {report.quality_score}/100 ({report.quality_label})
                      </span>
                    </div>

                    <div className="preview-summary-grid" style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", marginTop: 14, gap: 12 }}>
                      <article className="preview-summary-card" style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.04)" }}>
                        <span>Avg Missing</span>
                        <strong style={{ fontSize: 18 }}>{report.avg_missing_pct}%</strong>
                        <small>Null/empty values</small>
                      </article>
                      <article className="preview-summary-card" style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.04)" }}>
                        <span>Duplicate rows</span>
                        <strong style={{ fontSize: 18 }}>{numberFormatter.format(report.duplicate_rows)}</strong>
                        <small>{report.duplicate_pct}% of sample</small>
                      </article>
                      <article className="preview-summary-card" style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.04)" }}>
                        <span>Outliers</span>
                        <strong style={{ fontSize: 18 }}>{report.outlier_columns?.length || 0}</strong>
                        <small>{report.outlier_columns?.length ? "Columns flagged" : "No columns flagged"}</small>
                      </article>
                    </div>

                    {report.outlier_columns?.length ? (
                      <div style={{ marginTop: 14 }}>
                        <span className="schema-context-label" style={{ fontSize: 11, textTransform: "uppercase" }}>Outlier Fields</span>
                        <div className="schema-table-chip-grid" style={{ marginTop: 6 }}>
                          {report.outlier_columns.map(col => (
                            <span key={col} className="schema-table-chip" style={{ cursor: "default", borderColor: "rgba(239, 68, 68, 0.2)", background: "rgba(239, 68, 68, 0.04)" }}>
                              {col}
                            </span>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {report.missing_by_column && Object.keys(report.missing_by_column).length ? (
                      <div style={{ marginTop: 16 }}>
                        <span className="schema-context-label" style={{ fontSize: 11, textTransform: "uppercase" }}>Null counts by column</span>
                        <div className="schema-field-editor-list" style={{ marginTop: 8, maxHeight: 180, overflowY: "auto", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 10, padding: 8 }}>
                          {Object.entries(report.missing_by_column)
                            .filter(([_, stats]) => stats.count > 0)
                            .map(([col, stats]) => (
                              <div key={col} style={{ display: "flex", justifyContent: "space-between", padding: "6px 8px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: 13 }}>
                                <span style={{ color: "#a5b4fc" }}>{col}</span>
                                <span style={{ color: "#e5e7eb" }}>
                                  <strong>{numberFormatter.format(stats.count)}</strong> nulls ({stats.pct}%)
                                </span>
                              </div>
                            ))}
                          {!Object.values(report.missing_by_column).some(s => s.count > 0) ? (
                            <p className="helper-text" style={{ margin: 0, textAlign: "center", padding: "8px 0" }}>No missing values detected in any columns! 🎉</p>
                          ) : null}
                        </div>
                      </div>
                    ) : null}
                  </section>
                );
              })() : null}

              <section className="schema-context-card">
                <div className="schema-context-header">
                  <div>
                    <h4>Bot guidance</h4>
                    <p>Choose the tables the bot should use and describe what the database and fields actually mean.</p>
                  </div>
                  <span className="schema-context-pill">
                    {selectedTableCount}/{tables.length || 1} tables selected
                  </span>
                </div>

                <div className="schema-context-block">
                  <label className="schema-context-label" htmlFor="database-description">
                    Database description
                  </label>
                  <textarea
                    id="database-description"
                    className="schema-context-textarea"
                    rows={4}
                    maxLength={2000}
                    placeholder="Example: This database tracks ecommerce orders, customers, and fulfillment. Currency is USD and refunded orders keep their original total."
                    value={schemaContextDraft.databaseDescription}
                    onChange={(event) => handleDatabaseDescriptionChange(event.target.value)}
                  />
                  <div className="schema-context-meta">
                    <span>Share the business purpose, naming quirks, units, and any important rules.</span>
                    <span>{databaseDescriptionLength}/2000</span>
                  </div>
                </div>

                {tables.length ? (
                  <div className="schema-context-block">
                    <div className="schema-context-subhead">
                      <label className="schema-context-label">Tables to send to the bot</label>
                      <span>Unselected tables still preview here, but they stay out of the bot's schema context.</span>
                    </div>
                    <div className="schema-table-chip-grid">
                      {tables.map((table) => {
                        const isSelected = selectedTablesForContext.includes(table.name);
                        return (
                          <button
                            key={table.name}
                            type="button"
                            className={`schema-table-chip ${isSelected ? "selected" : ""}`}
                            aria-pressed={isSelected}
                            onClick={() => handleTableSelectionToggle(table.name)}
                          >
                            <span>{table.name}</span>
                            <small>{numberFormatter.format(table.row_count ?? 0)} rows</small>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ) : null}

                {selectedTableMeta ? (
                  <div className="schema-context-block">
                    <div className="schema-context-subhead">
                      <label className="schema-context-label" htmlFor="table-description">
                        Description for {selectedTableMeta.name}
                      </label>
                      <span>
                        {selectedTablesForContext.includes(selectedTableMeta.name)
                          ? "This table is currently included in the bot context."
                          : "Select this table above if you want the bot to use it."}
                      </span>
                    </div>
                    <textarea
                      id="table-description"
                      className="schema-context-textarea"
                      rows={3}
                      maxLength={2000}
                      placeholder={`Example: ${selectedTableMeta.name} stores the final order-level record after checkout, one row per order.`}
                      value={currentTableDescription}
                      onChange={(event) => handleTableDescriptionChange(selectedTableMeta.name, event.target.value)}
                    />
                  </div>
                ) : null}

                {previewFields.length ? (
                  <div className="schema-context-block">
                    <div className="schema-context-subhead">
                      <label className="schema-context-label">Field descriptions for {selectedTableMeta?.name}</label>
                      <span>Explain the business meaning, enum values, calculations, and units where it helps.</span>
                    </div>
                    <div className="schema-field-editor-list">
                      {previewFields.map((field) => (
                        <article key={field.name} className="schema-field-editor">
                          <div className="schema-field-editor-head">
                            <strong>{field.name}</strong>
                            <span>{field.type || "field"}</span>
                          </div>
                          <textarea
                            className="schema-context-textarea schema-field-textarea"
                            rows={2}
                            maxLength={2000}
                            placeholder={`Describe ${field.name} so the bot understands how to use it.`}
                            value={currentFieldDescriptions[field.name] || ""}
                            onChange={(event) => handleFieldDescriptionChange(selectedTableMeta?.name || "", field.name, event.target.value)}
                          />
                        </article>
                      ))}
                    </div>
                  </div>
                ) : null}

                <div className="schema-context-actions">
                  <p className="helper-text">
                    These notes are added to the schema prompt so the assistant can answer with better context and fewer wrong assumptions.
                  </p>
                  <div className="schema-context-save-row">
                    {schemaContextStatus ? (
                      <div className={`schema-context-status ${schemaContextStatus.tone}`}>
                        {schemaContextStatus.message}
                      </div>
                    ) : null}
                    <button
                      type="button"
                      className="btn-primary schema-context-save"
                      onClick={handleSaveSchemaContext}
                      disabled={savingContext || !tables.length}
                    >
                      {savingContext ? "Saving..." : "Save bot guidance"}
                    </button>
                  </div>
                </div>
              </section>

              {visibleFields.length ? (
                <div className="preview-field-grid">
                  {visibleFields.map((field) => (
                    <article key={field.name} className="preview-field-card">
                      <span>{formatColumnLabel(field.name)}</span>
                      <strong>{field.type || "field"}</strong>
                      <small>{formatFieldSamples(field)}</small>
                    </article>
                  ))}
                  {hiddenFieldCount ? (
                    <article className="preview-field-card preview-field-card-muted">
                      <span>More fields</span>
                      <strong>+{hiddenFieldCount}</strong>
                      <small>Open rows to inspect every column</small>
                    </article>
                  ) : null}
                </div>
              ) : null}

              {hasChart ? (
                renderChart()
              ) : null}

              {!hasChart ? (
                <div className="info-banner preview-message">
                  <BarChart3 size={18} />
                  No graphable pattern detected yet for this table.
                </div>
              ) : null}
            </>
          ) : (
            <div className="empty-state preview-empty">
              <span className="empty-state-icon">
                {sourceType === "csv" || sourceType === "excel" ? <FileSpreadsheet size={24} /> : <Database size={24} />}
              </span>
              <div>
                <h3 style={{ margin: 0, fontFamily: "var(--font-display)" }}>Preview ready after connect</h3>
                <p className="empty-copy" style={{ margin: "10px 0 0" }}>
                  Upload a file or connect a database to inspect rows here while you chat.
                </p>
              </div>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
