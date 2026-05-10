"use client";

import React, { useEffect, useState } from "react";
import { Database, Sparkles, UploadCloud, X } from "lucide-react";
import api from "@/lib/api";
import { validateSourceConnectionUri } from "@/lib/source-validation";

interface ConnectorModalProps {
  sessionId: string;
  initialTab?: TabId;
  mode?: "all" | "database" | "file";
  onClose: () => void;
  onConnect: (sourceConfig?: {
    type?: string;
    file_name?: string | null;
    database_name?: string | null;
    connection_uri?: string | null;
  }) => void;
}

type TabId = "mongodb" | "postgresql" | "file";

interface SavedSource {
  id: string;
  source_type: "mongodb" | "postgresql";
  display_name: string;
  database_name?: string | null;
  masked_uri: string;
  updated_at?: string | null;
}

function isDatabaseTab(tab: TabId): tab is Exclude<TabId, "file"> {
  return tab !== "file";
}

function getSavedConnectionTab(connectionType: string | undefined, fallbackTab: TabId): Exclude<TabId, "file"> {
  if (connectionType === "mongodb" || connectionType === "postgresql") {
    return connectionType;
  }

  return isDatabaseTab(fallbackTab) ? fallbackTab : "mongodb";
}

function getDbPlaceholder(activeTab: TabId) {
  if (activeTab === "mongodb") {
    return "mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority";
  }
  return "postgresql://postgres.project:password@aws-0-region.pooler.supabase.com:6543/postgres?sslmode=require";
}

function readErrorMessage(err: unknown, fallback: string) {
  return (
    (typeof err === "object" &&
      err &&
      "response" in err &&
      typeof (err as { response?: { data?: { message?: string } } }).response?.data?.message === "string" &&
      (err as { response?: { data?: { message?: string } } }).response?.data?.message) ||
    fallback
  );
}

export default function ConnectorModal({
  sessionId,
  initialTab = "mongodb",
  mode = "all",
  onClose,
  onConnect,
}: ConnectorModalProps) {
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);
  const [uri, setUri] = useState("");
  const [dbName, setDbName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedConnections, setSavedConnections] = useState<SavedSource[]>([]);
  const [savedMenuOpen, setSavedMenuOpen] = useState(false);
  const [saveToLibrary, setSaveToLibrary] = useState(true);

  useEffect(() => {
    // Keep the tab aligned with the parent route when the connector modal is reopened in a different mode.
    setActiveTab(initialTab);
  }, [initialTab]);

  useEffect(() => {
    const fetchSavedConnections = async () => {
      try {
        const response = await api.get("/connectors/library");
        setSavedConnections(response.data.data || []);
      } catch (fetchError) {
        console.error("Failed to load saved sources", fetchError);
      }
    };

    void fetchSavedConnections();
  }, []);

  const connectDatabase = async (selectedTab: Exclude<TabId, "file">, connectionUri: string, databaseNameValue = "") => {
    if (!sessionId) {
      setError("Create or open a chat session before connecting a source.");
      return;
    }

    if (!connectionUri.trim()) {
      setError("Enter a connection URI before connecting.");
      return;
    }

    if (selectedTab === "mongodb" && !databaseNameValue.trim()) {
      setError("MongoDB quick connect needs a database name.");
      return;
    }

    const validation = validateSourceConnectionUri(selectedTab, connectionUri, databaseNameValue);
    if (!validation.ok) {
      setError(validation.message || "The connection URI is invalid.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const config: Record<string, string | boolean> = {
        type: selectedTab,
        connection_uri: connectionUri.trim(),
        save_to_library: saveToLibrary,
      };
      if (selectedTab === "mongodb") {
        config.database_name = databaseNameValue.trim();
      }

      const response = await api.post(`/connectors/${sessionId}/connect`, config);
      onConnect({
        type: response.data.data?.source_type || selectedTab,
        database_name: response.data.data?.database_name || (selectedTab === "mongodb" ? databaseNameValue.trim() : null),
        connection_uri: response.data.data?.connection_uri || null,
      });
      onClose();
    } catch (err: unknown) {
      setError(readErrorMessage(err, "Failed to connect to the selected source."));
    } finally {
      setLoading(false);
    }
  };

  const handleConnectDb = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!isDatabaseTab(activeTab)) {
      return;
    }

    await connectDatabase(activeTab, uri, dbName);
  };

  const handleSavedConnectionSelect = async (connection: SavedSource) => {
    const selectedTab = getSavedConnectionTab(connection.source_type, activeTab);
    setActiveTab(selectedTab);
    setSavedMenuOpen(false);
    setLoading(true);
    setError(null);

    try {
      const response = await api.post(`/connectors/${sessionId}/connect/saved/${connection.id}`);
      onConnect({
        type: response.data.data?.source_type || selectedTab,
        database_name: response.data.data?.database_name || connection.database_name || null,
        connection_uri: response.data.data?.connection_uri || connection.masked_uri,
      });
      onClose();
    } catch (err: unknown) {
      setError(readErrorMessage(err, "Failed to connect to the saved source."));
    } finally {
      setLoading(false);
    }
  };

  const handleUploadFile = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!sessionId) {
      setError("Create or open a chat session before uploading a file.");
      return;
    }
    if (!file) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await api.post(`/connectors/${sessionId}/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      onConnect({
        type: response.data.data?.source_type || "csv",
        file_name: response.data.data?.file_name || file.name,
      });
      onClose();
    } catch (err: unknown) {
      setError(readErrorMessage(err, "Failed to upload file."));
    } finally {
      setLoading(false);
    }
  };

  const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
    { id: "file", label: "Files", icon: <UploadCloud size={16} /> },
    { id: "mongodb", label: "MongoDB", icon: <Database size={16} /> },
    { id: "postgresql", label: "PostgreSQL", icon: <Database size={16} /> },
  ];

  let tabsToRender = tabs;
  if (mode === "database") {
    tabsToRender = tabs.filter((tab) => tab.id !== "file");
  } else if (mode === "file") {
    tabsToRender = tabs.filter((tab) => tab.id === "file");
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <div className="modal-head">
          <div>
            <div className="brand-row">
              <span className="brand-mark">
                <Database size={18} />
              </span>
              Connect data
            </div>
            <h3 style={{ marginTop: 18 }}>Bring in files or databases before analysis</h3>
            <p className="helper-text" style={{ marginTop: 8 }}>
              Connect MongoDB Atlas, Supabase PostgreSQL, or upload a dataset. Raw connection secrets stay on the server after validation.
            </p>
          </div>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close modal">
            <X size={18} />
          </button>
        </div>

        <div className="tab-row">
          {tabsToRender.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`tab-button ${activeTab === tab.id ? "active" : ""}`}
              onClick={() => {
                setActiveTab(tab.id);
                setError(null);
              }}
            >
              {tab.icon}
              <span style={{ marginLeft: "8px" }}>{tab.label}</span>
            </button>
          ))}
        </div>

        {error ? (
          <div className="error-banner" style={{ marginTop: 0, marginBottom: 18 }}>
            <Sparkles size={18} />
            {error}
          </div>
        ) : null}

        {activeTab === "file" ? (
          <form key="file-form" className="field-stack" onSubmit={handleUploadFile}>
            <div className="info-banner connector-security-note">
              <Sparkles size={18} />
              CSV is the lightest option for quick analysis. Excel and parquet uploads also preview and can be queried in-chat.
            </div>
            <div className="field">
              <label htmlFor="file-upload">Upload CSV, Excel, or parquet</label>
              <input
                id="file-upload"
                className="file-input"
                type="file"
                accept=".csv,.xlsx,.xls,.parquet"
                onChange={(event) => setFile(event.target.files?.[0] || null)}
                required
              />
            </div>
            <div className="composer-footer">
              <p className="helper-text">Best for quick testing, lightweight dashboards, and ad hoc chat analysis.</p>
              <button type="submit" className="btn-primary" disabled={loading || !file}>
                {loading ? "Uploading..." : "Upload and connect"}
              </button>
            </div>
          </form>
        ) : loading ? (
          <div className="db-connecting-animation">
            <div className="db-plug-container">
              <div className="db-plug left"><Database size={24} /></div>
              <div className="db-data-stream"></div>
              <div className="db-plug right"><Database size={24} /></div>
            </div>
            <p className="db-connecting-text">Establishing connection...</p>
          </div>
        ) : (
          <form key={`db-form-${activeTab}`} className="field-stack" onSubmit={handleConnectDb}>
            <div className="saved-connections-block">
              <div className="saved-connections-header">
                <label className="saved-connections-label">Saved server-side sources</label>
                <button
                  type="button"
                  className="saved-connections-trigger"
                  onClick={() => setSavedMenuOpen((current) => !current)}
                  aria-expanded={savedMenuOpen}
                >
                  Secure library
                </button>
              </div>

              {savedMenuOpen ? (
                <div className="saved-connections-menu" role="listbox" aria-label="Saved connections">
                  {savedConnections.length ? (
                    savedConnections.map((connection) => (
                      <div key={connection.id} className="saved-connection-item">
                        <button
                          type="button"
                          className="saved-connection-select"
                          onClick={() => {
                            void handleSavedConnectionSelect(connection);
                          }}
                        >
                          <strong>{connection.display_name}</strong>
                          <span>{connection.source_type === "mongodb" ? "MongoDB Atlas" : "Supabase PostgreSQL"}</span>
                          <span className="saved-source-meta">{connection.masked_uri}</span>
                        </button>
                      </div>
                    ))
                  ) : (
                    <div className="saved-connections-empty">No saved sources yet for this account</div>
                  )}
                </div>
              ) : null}
            </div>

            <div className="info-banner connector-security-note">
              <Sparkles size={18} />
              Only MongoDB Atlas and Supabase PostgreSQL are allowed here. Private-network and localhost URLs are blocked.
            </div>

            <div className="field">
              <label htmlFor="connection-uri">Connection URI</label>
              <input
                id="connection-uri"
                type="text"
                placeholder={getDbPlaceholder(activeTab)}
                value={uri}
                onChange={(event) => setUri(event.target.value)}
                required
              />
            </div>
            {activeTab === "mongodb" ? (
              <div className="field">
                <label htmlFor="database-name">Database name</label>
                <input
                  id="database-name"
                  type="text"
                  placeholder="analytics"
                  value={dbName}
                  onChange={(event) => setDbName(event.target.value)}
                  required
                />
              </div>
            ) : null}
            <label className="saved-source-checkbox">
              <input
                type="checkbox"
                checked={saveToLibrary}
                onChange={(event) => setSaveToLibrary(event.target.checked)}
              />
              <span>Save this validated source to my secure server-side library</span>
            </label>
            <div className="composer-footer">
              <p className="helper-text">Attach your live source to let the chatbot query real tables, persist schema notes, and generate visuals.</p>
              <button type="submit" className="btn-primary" disabled={loading || !uri}>
                {loading ? "Connecting..." : "Connect source"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
