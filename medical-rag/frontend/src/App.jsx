import { useEffect, useMemo, useState } from 'react';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5200';

export default function App() {
  const [backendHealth, setBackendHealth] = useState('unknown');
  const [knowledgeBases, setKnowledgeBases] = useState([]);
  const [activeKnowledgeBase, setActiveKnowledgeBase] = useState('default');
  const [newKnowledgeBaseName, setNewKnowledgeBaseName] = useState('');
  const [kbMessage, setKbMessage] = useState('');
  const [kbError, setKbError] = useState('');
  const [creatingKnowledgeBase, setCreatingKnowledgeBase] = useState(false);
  const [switchingKnowledgeBase, setSwitchingKnowledgeBase] = useState(false);
  const [deletingKnowledgeBase, setDeletingKnowledgeBase] = useState(false);
  const [kbDeleteConfirm, setKbDeleteConfirm] = useState('');
  const [settings, setSettings] = useState(null);
  const [editSettings, setEditSettings] = useState(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState('');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [sources, setSources] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [ingestStatus, setIngestStatus] = useState(null);
  const [ingestError, setIngestError] = useState('');
  const [chunkSize, setChunkSize] = useState(800);
  const [chunkOverlap, setChunkOverlap] = useState(120);
  const [replaceCollection, setReplaceCollection] = useState(false);

  const canAsk = useMemo(() => question.trim().length > 0 && !loading, [question, loading]);
  const canUpload = useMemo(() => selectedFiles.length > 0 && !uploading, [selectedFiles, uploading]);
  const canIngest = useMemo(() => !ingesting && !uploading, [ingesting, uploading]);
  const canClearData = useMemo(() => !ingesting && !uploading, [ingesting, uploading]);
  const canCreateKnowledgeBase = useMemo(
    () => newKnowledgeBaseName.trim().length > 0 && !creatingKnowledgeBase,
    [newKnowledgeBaseName, creatingKnowledgeBase]
  );
  const ingestProgress = ingestStatus?.progress || null;

  const withKnowledgeBase = (path, knowledgeBaseOverride = null) => {
    const kb = (knowledgeBaseOverride || activeKnowledgeBase)?.trim();
    if (!kb) {
      return `${API_BASE_URL}${path}`;
    }

    const joiner = path.includes('?') ? '&' : '?';
    return `${API_BASE_URL}${path}${joiner}knowledge_base=${encodeURIComponent(kb)}`;
  };

  const overallProgressPercent = useMemo(() => {
    if (!ingestProgress || !ingestProgress.total_files) {
      return 0;
    }

    const completed = Number(ingestProgress.completed_files || 0);
    const current = Number(ingestProgress.current_file_progress || 0) / 100;
    const pct = ((completed + current) / ingestProgress.total_files) * 100;
    return Math.max(0, Math.min(100, Math.round(pct)));
  }, [ingestProgress]);

  const refreshDocuments = async (knowledgeBaseOverride = null) => {
    try {
      const response = await fetch(withKnowledgeBase('/documents', knowledgeBaseOverride));
      if (!response.ok) {
        throw new Error(`Failed to fetch documents (${response.status})`);
      }

      const data = await response.json();
      setDocuments(Array.isArray(data.documents) ? data.documents : []);
    } catch (err) {
      setError(err.message || 'Failed to load documents.');
    }
  };

  const refreshBackendHealth = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/health`);
      setBackendHealth(response.ok ? 'online' : 'degraded');
    } catch {
      setBackendHealth('offline');
    }
  };

  const refreshSettings = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/settings`);
      if (!response.ok) {
        throw new Error(`Failed to fetch settings (${response.status})`);
      }

      const data = await response.json();
      setSettings(data);
      if (data.active_knowledge_base) {
        setActiveKnowledgeBase(data.active_knowledge_base);
      }
      setEditSettings({
        llm_model: data.llm_model,
        llm_temperature: data.llm_temperature,
        ollama_num_ctx: data.ollama_num_ctx,
        ollama_num_predict: data.ollama_num_predict,
        retriever_top_k: data.retriever_top_k,
        ingest_chunk_size: data.ingest_chunk_size,
        ingest_chunk_overlap: data.ingest_chunk_overlap,
      });
    } catch (err) {
      setError(err.message || 'Failed to load settings.');
    }
  };

  const refreshKnowledgeBases = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/knowledge-bases`);
      if (!response.ok) {
        throw new Error(`Failed to fetch knowledge bases (${response.status})`);
      }

      const data = await response.json();
      const list = Array.isArray(data.knowledge_bases) ? data.knowledge_bases : [];
      setKnowledgeBases(list);

      if (data.active_knowledge_base) {
        setActiveKnowledgeBase(data.active_knowledge_base);
        return data.active_knowledge_base;
      } else if (list.length > 0 && !list.includes(activeKnowledgeBase)) {
        setActiveKnowledgeBase(list[0]);
        return list[0];
      }

      return activeKnowledgeBase;
    } catch (err) {
      setKbError(err.message || 'Failed to load knowledge bases.');
      return activeKnowledgeBase;
    }
  };

  const handleKnowledgeBaseSwitch = async (nextKnowledgeBase) => {
    if (!nextKnowledgeBase || switchingKnowledgeBase) {
      return;
    }

    setKbError('');
    setKbMessage('');
    setSwitchingKnowledgeBase(true);

    try {
      const response = await fetch(`${API_BASE_URL}/knowledge-bases/active`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ knowledge_base: nextKnowledgeBase }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || `Failed to switch knowledge base (${response.status})`);
      }

      setActiveKnowledgeBase(nextKnowledgeBase);
      setKbMessage(`Active knowledge base: ${nextKnowledgeBase}`);
      await refreshKnowledgeBases();
      await refreshDocuments(nextKnowledgeBase);
      await fetchIngestStatus(nextKnowledgeBase);
      await refreshSettings();
      setAnswer('');
      setSources([]);
    } catch (err) {
      setKbError(err.message || 'Failed to switch knowledge base.');
    } finally {
      setSwitchingKnowledgeBase(false);
    }
  };

  const handleKnowledgeBaseCreate = async (event) => {
    event.preventDefault();
    if (!canCreateKnowledgeBase) {
      return;
    }

    const candidate = newKnowledgeBaseName.trim();
    setCreatingKnowledgeBase(true);
    setKbError('');
    setKbMessage('');

    try {
      const response = await fetch(`${API_BASE_URL}/knowledge-bases`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ knowledge_base: candidate }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || `Failed to create knowledge base (${response.status})`);
      }

      setNewKnowledgeBaseName('');
      await refreshKnowledgeBases();
      setKbMessage(`Knowledge base created: ${candidate}`);
      await handleKnowledgeBaseSwitch(candidate);
    } catch (err) {
      setKbError(err.message || 'Failed to create knowledge base.');
    } finally {
      setCreatingKnowledgeBase(false);
    }
  };

  const handleKnowledgeBaseDelete = async (event) => {
    event.preventDefault();
    if (!kbDeleteConfirm) {
      return;
    }

    const kbToDelete = kbDeleteConfirm.trim();
    setDeletingKnowledgeBase(true);
    setKbError('');
    setKbMessage('');

    try {
      const response = await fetch(`${API_BASE_URL}/knowledge-bases/${encodeURIComponent(kbToDelete)}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || `Failed to delete knowledge base (${response.status})`);
      }

      setKbDeleteConfirm('');
      await refreshKnowledgeBases();
      setKbMessage(`Knowledge base deleted: ${kbToDelete}`);
      await refreshDocuments();
      await fetchIngestStatus();
      await refreshSettings();
      setAnswer('');
      setSources([]);
    } catch (err) {
      setKbError(err.message || 'Failed to delete knowledge base.');
    } finally {
      setDeletingKnowledgeBase(false);
    }
  };

  const handleSettingChange = (key, value) => {
    setEditSettings((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const handleSaveSettings = async (event) => {
    event.preventDefault();
    if (!editSettings || savingSettings) {
      return;
    }

    setSavingSettings(true);
    setSettingsMessage('');
    setError('');

    try {
      const payload = {
        llm_model: String(editSettings.llm_model).trim(),
        llm_temperature: Number(editSettings.llm_temperature),
        ollama_num_ctx: Number(editSettings.ollama_num_ctx),
        ollama_num_predict: Number(editSettings.ollama_num_predict),
        retriever_top_k: Number(editSettings.retriever_top_k),
        ingest_chunk_size: Number(editSettings.ingest_chunk_size),
        ingest_chunk_overlap: Number(editSettings.ingest_chunk_overlap),
      };

      const response = await fetch(`${API_BASE_URL}/settings`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || `Failed to save settings (${response.status})`);
      }

      setSettings(data.settings || null);
      setChunkSize(data.settings?.ingest_chunk_size ?? editSettings.ingest_chunk_size);
      setChunkOverlap(data.settings?.ingest_chunk_overlap ?? editSettings.ingest_chunk_overlap);
      setSettingsMessage('Settings saved. New values are active for new queries.');
    } catch (err) {
      setSettingsMessage('');
      setError(err.message || 'Failed to save settings.');
    } finally {
      setSavingSettings(false);
    }
  };

  const handleClearData = async () => {
    if (ingesting) {
      setError('Cannot clear data while ingestion is running. Wait for completion, then clear.');
      return;
    }

    const confirmed = window.confirm(
      'Clear uploaded PDFs and delete the current vectorstore collection? This will remove previously ingested data.'
    );

    if (!confirmed) {
      return;
    }

    setError('');
    setIngestError('');
    setSettingsMessage('');

    try {
      const response = await fetch(`${API_BASE_URL}/data/clear`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          delete_files: true,
          delete_vectorstore: true,
          knowledge_base: activeKnowledgeBase,
        }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 409) {
          throw new Error('Cannot clear data while ingestion is running. Wait for completion, then clear.');
        }
        throw new Error(data.detail || `Failed to clear data (${response.status})`);
      }

      setDocuments([]);
      setIngestStatus({
        status: 'idle',
        job_id: null,
        started_at: null,
        finished_at: null,
        error: null,
        result: null,
        progress: null,
      });
      setIngesting(false);
      refreshSettings();
      setSettingsMessage(
        `Cleared ${Array.isArray(data.deleted_files) ? data.deleted_files.length : 0} files in ${activeKnowledgeBase}${data.deleted_vectorstore ? ' and vectorstore collection.' : '.'}`
      );
    } catch (err) {
      setError(err.message || 'Failed to clear data.');
    }
  };

  const fetchIngestStatus = async (knowledgeBaseOverride = null) => {
    const kb = knowledgeBaseOverride || activeKnowledgeBase;
    try {
      const response = await fetch(
        `${API_BASE_URL}/ingest/status?knowledge_base=${encodeURIComponent(kb)}`
      );
      if (!response.ok) {
        throw new Error(`Failed to fetch ingest status (${response.status})`);
      }

      const data = await response.json();
      setIngestStatus(data);
      setIngesting(data.status === 'running');

      if (data.status === 'completed') {
        setIngestError('');
        refreshDocuments();
      }

      if (data.status === 'failed') {
        setIngestError(data.error || 'Ingestion failed.');
      }
    } catch (err) {
      setIngestError(err.message || 'Failed to read ingest status.');
      setIngesting(false);
    }
  };

  useEffect(() => {
    const bootstrap = async () => {
      await refreshBackendHealth();
      const initialKnowledgeBase = await refreshKnowledgeBases();
      await refreshSettings();
      await refreshDocuments(initialKnowledgeBase);
      await fetchIngestStatus(initialKnowledgeBase);
    };

    bootstrap();
  }, []);

  useEffect(() => {
    if (!ingesting) {
      return undefined;
    }

    const timer = setInterval(fetchIngestStatus, 2000);
    return () => clearInterval(timer);
  }, [ingesting, activeKnowledgeBase]);

  const handleFileSelection = (event) => {
    const files = Array.from(event.target.files || []);
    setSelectedFiles(files);
  };

  const handleUpload = async (event) => {
    event.preventDefault();
    if (!canUpload) {
      return;
    }

    setUploading(true);
    setError('');

    try {
      const formData = new FormData();
      selectedFiles.forEach((file) => formData.append('files', file));

      const response = await fetch(withKnowledgeBase('/upload'), {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Upload failed (${response.status})`);
      }

      setSelectedFiles([]);
      await refreshDocuments();
    } catch (err) {
      setError(err.message || 'Upload failed.');
    } finally {
      setUploading(false);
    }
  };

  const handleIngestStart = async (event) => {
    event.preventDefault();
    if (!canIngest) {
      return;
    }

    setIngestError('');

    try {
      const response = await fetch(`${API_BASE_URL}/ingest/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          chunk_size: Number(chunkSize),
          chunk_overlap: Number(chunkOverlap),
          replace_collection: replaceCollection,
          knowledge_base: activeKnowledgeBase,
        }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Failed to start ingest (${response.status})`);
      }

      setIngesting(true);
      await fetchIngestStatus();
    } catch (err) {
      setIngestError(err.message || 'Failed to start ingest.');
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!canAsk) {
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await fetch(`${API_BASE_URL}/ask`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: question.trim(),
          knowledge_base: activeKnowledgeBase,
        }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Request failed with status ${response.status}`);
      }

      const data = await response.json();
      setAnswer(data.answer || 'No answer returned.');
      setSources(Array.isArray(data.sources) ? data.sources : []);
    } catch (err) {
      setAnswer('');
      setSources([]);
      setError(err.message || 'Failed to query backend.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="page">
      <section className="card">
        <h1>Medical RAG Assistant</h1>
        <p className="subtitle">Ask questions over your ingested medical documents.</p>

        <section className="ingest-panel">
          <h2>Knowledge Bases</h2>
          <p className="meta">
            Active knowledge base: <strong>{activeKnowledgeBase}</strong>
          </p>

          <form className="kb-switch-row" onSubmit={(event) => event.preventDefault()}>
            <label htmlFor="kb-select">Select knowledge base</label>
            <select
              id="kb-select"
              value={activeKnowledgeBase}
              onChange={(e) => handleKnowledgeBaseSwitch(e.target.value)}
              disabled={switchingKnowledgeBase || ingesting}
            >
              {knowledgeBases.length === 0 ? (
                <option value="default">default</option>
              ) : (
                knowledgeBases.map((kb) => (
                  <option key={kb} value={kb}>
                    {kb}
                  </option>
                ))
              )}
            </select>
          </form>

          <form className="kb-create-row" onSubmit={handleKnowledgeBaseCreate}>
            <label htmlFor="kb-new">Create new knowledge base folder</label>
            <input
              id="kb-new"
              type="text"
              value={newKnowledgeBaseName}
              onChange={(e) => setNewKnowledgeBaseName(e.target.value)}
              placeholder="Example: endocrinology-set-2"
              disabled={creatingKnowledgeBase || ingesting}
            />
            <button type="submit" disabled={!canCreateKnowledgeBase || ingesting}>
              {creatingKnowledgeBase ? 'Creating...' : 'Create and switch'}
            </button>
          </form>

          <form className="kb-delete-row" onSubmit={handleKnowledgeBaseDelete}>
            <fieldset>
              <legend>Delete knowledge base folder</legend>
              {kbDeleteConfirm !== '' && (
                <div className="warning-box">
                  <p><strong>⚠️ This will permanently delete:</strong></p>
                  <ul>
                    <li>All documents in the <code>{kbDeleteConfirm}</code> folder</li>
                    <li>All vectors in the database collection</li>
                    <li>All ingestion history</li>
                  </ul>
                  <p>This cannot be undone. Are you sure?</p>
                </div>
              )}
              <select
                value={kbDeleteConfirm}
                onChange={(e) => setKbDeleteConfirm(e.target.value)}
                disabled={deletingKnowledgeBase || ingesting}
              >
                <option value="">Select knowledge base to delete...</option>
                {knowledgeBases.map((kb) => (
                  kb !== 'default' && (
                    <option key={kb} value={kb}>
                      {kb}
                    </option>
                  )
                ))}
              </select>
              <button 
                type="submit" 
                disabled={kbDeleteConfirm === '' || deletingKnowledgeBase || ingesting}
                className="danger-button"
              >
                {deletingKnowledgeBase ? 'Deleting...' : 'Delete'}
              </button>
            </fieldset>
          </form>

          {kbMessage ? <p className="ok-text">{kbMessage}</p> : null}
          {kbError ? <p className="error">{kbError}</p> : null}

          <div className="status-row">
            <span className={`health-pill health-${backendHealth}`}>Backend: {backendHealth}</span>
            <div className="toolbar-buttons">
              <button type="button" className="secondary-button" onClick={() => { refreshBackendHealth(); refreshKnowledgeBases(); refreshSettings(); refreshDocuments(); fetchIngestStatus(); }}>
                Refresh dashboard
              </button>
              <button type="button" className="danger-button" onClick={handleClearData} disabled={!canClearData}>
                {ingesting ? 'Clear disabled during ingest' : 'Clear data'}
              </button>
            </div>
          </div>

          <h2>Current Settings</h2>
          {settings && editSettings ? (
            <form className="settings-form" onSubmit={handleSaveSettings}>
              <div className="settings-grid">
                <div><strong>LLM provider:</strong> {settings.llm_provider}</div>
                <div><strong>Embedding provider:</strong> {settings.embedding_provider}</div>
                <div><strong>Embedding model:</strong> {settings.embedding_model}</div>
                <div><strong>Collection:</strong> {settings.collection_name}</div>
              </div>

              <label htmlFor="llm-model">LLM model</label>
              <input
                id="llm-model"
                type="text"
                value={editSettings.llm_model}
                onChange={(e) => handleSettingChange('llm_model', e.target.value)}
              />

              <label htmlFor="llm-temp">Temperature</label>
              <input
                id="llm-temp"
                type="number"
                step="0.1"
                min="0"
                value={editSettings.llm_temperature}
                onChange={(e) => handleSettingChange('llm_temperature', e.target.value)}
              />

              <label htmlFor="num-ctx">Context size</label>
              <input
                id="num-ctx"
                type="number"
                min="1"
                value={editSettings.ollama_num_ctx}
                onChange={(e) => handleSettingChange('ollama_num_ctx', e.target.value)}
              />

              <label htmlFor="num-predict">Max output tokens</label>
              <input
                id="num-predict"
                type="number"
                min="1"
                value={editSettings.ollama_num_predict}
                onChange={(e) => handleSettingChange('ollama_num_predict', e.target.value)}
              />

              <label htmlFor="top-k">Retriever top-k</label>
              <input
                id="top-k"
                type="number"
                min="1"
                value={editSettings.retriever_top_k}
                onChange={(e) => handleSettingChange('retriever_top_k', e.target.value)}
              />

              <label htmlFor="ingest-size">Default ingest chunk size</label>
              <input
                id="ingest-size"
                type="number"
                min="100"
                value={editSettings.ingest_chunk_size}
                onChange={(e) => handleSettingChange('ingest_chunk_size', e.target.value)}
              />

              <label htmlFor="ingest-overlap">Default ingest chunk overlap</label>
              <input
                id="ingest-overlap"
                type="number"
                min="0"
                value={editSettings.ingest_chunk_overlap}
                onChange={(e) => handleSettingChange('ingest_chunk_overlap', e.target.value)}
              />

              <button type="submit" disabled={savingSettings}>
                {savingSettings ? 'Saving...' : 'Save Settings'}
              </button>
            </form>
          ) : (
            <p className="meta">Loading settings...</p>
          )}
          {settingsMessage ? <p className="ok-text">{settingsMessage}</p> : null}

          <h2>Ingestion</h2>
          <p className="meta">Uploaded documents: {documents.length}</p>

          <form onSubmit={handleUpload} className="query-form">
            <label htmlFor="files">Upload PDFs</label>
            <input id="files" type="file" accept="application/pdf" multiple onChange={handleFileSelection} />
            <button type="submit" disabled={!canUpload}>
              {uploading ? 'Uploading...' : 'Upload'}
            </button>
          </form>

          <form onSubmit={handleIngestStart} className="ingest-form">
            <label htmlFor="chunk-size">Chunk Size</label>
            <input
              id="chunk-size"
              type="number"
              min="100"
              value={chunkSize}
              onChange={(e) => setChunkSize(e.target.value)}
            />

            <label htmlFor="chunk-overlap">Chunk Overlap</label>
            <input
              id="chunk-overlap"
              type="number"
              min="0"
              value={chunkOverlap}
              onChange={(e) => setChunkOverlap(e.target.value)}
            />

            <label className="checkbox-row" htmlFor="replace-collection">
              <input
                id="replace-collection"
                type="checkbox"
                checked={replaceCollection}
                onChange={(e) => setReplaceCollection(e.target.checked)}
              />
              Replace existing vector collection
            </label>

            <button type="submit" disabled={!canIngest}>
              {ingesting ? 'Ingesting...' : 'Start Ingestion'}
            </button>
          </form>

          {ingestStatus ? (
            <div className="status-box">
              <p><strong>Status:</strong> {ingestStatus.status}</p>
              {ingestStatus.job_id ? <p><strong>Job:</strong> {ingestStatus.job_id}</p> : null}
              {ingestStatus.started_at ? <p><strong>Started:</strong> {ingestStatus.started_at}</p> : null}
              {ingestStatus.finished_at ? <p><strong>Finished:</strong> {ingestStatus.finished_at}</p> : null}
              {ingestProgress ? (
                <>
                  <p>
                    <strong>Overall:</strong> {overallProgressPercent}% ({ingestProgress.completed_files || 0}/{ingestProgress.total_files || 0} files)
                  </p>
                  <div className="progress-track">
                    <div className="progress-fill" style={{ width: `${overallProgressPercent}%` }} />
                  </div>

                  <p>
                    <strong>Current file:</strong> {ingestProgress.current_file || 'N/A'} ({ingestProgress.current_file_progress || 0}%)
                  </p>
                  <div className="progress-track">
                    <div className="progress-fill current-file" style={{ width: `${ingestProgress.current_file_progress || 0}%` }} />
                  </div>

                  {Array.isArray(ingestProgress.files) && ingestProgress.files.length > 0 ? (
                    <div className="file-progress-list">
                      {ingestProgress.files.map((file) => (
                        <div key={file.file} className="file-progress-item">
                          <div className="file-progress-header">
                            <span>{file.file}</span>
                            <span>{file.status}</span>
                          </div>
                          <div className="progress-track slim">
                            <div className="progress-fill" style={{ width: `${file.progress || 0}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </>
              ) : null}
              {ingestStatus.result ? (
                <p>
                  <strong>Result:</strong> scanned {ingestStatus.result.scanned_files}, parsed {ingestStatus.result.parsed_documents}, chunks {ingestStatus.result.chunks_created}
                </p>
              ) : null}
              {ingestStatus.result?.failed_files?.length ? (
                <div>
                  <strong>Failed files:</strong>
                  <ul>
                    {ingestStatus.result.failed_files.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}

          {ingestError ? <p className="error">{ingestError}</p> : null}
          {documents.length > 0 ? (
            <ul>
              {documents.map((doc) => (
                <li key={doc}>{doc}</li>
              ))}
            </ul>
          ) : (
            <p className="meta">No PDFs uploaded yet.</p>
          )}
        </section>

        <form onSubmit={handleSubmit} className="query-form">
          <label htmlFor="question">Question</label>
          <textarea
            id="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Example: What abnormal lab values are reported?"
            rows={4}
          />
          <button type="submit" disabled={!canAsk}>
            {loading ? 'Thinking...' : 'Ask'}
          </button>
        </form>

        {error ? <p className="error">{error}</p> : null}

        <section className="result">
          <h2>Answer</h2>
          <p>{answer || 'Submit a question to see an answer.'}</p>
        </section>

        <section className="sources">
          <h2>Sources</h2>
          {sources.length === 0 ? (
            <p>No sources returned yet.</p>
          ) : (
            <ul>
              {sources.map((source, index) => (
                <li key={`${source.source || 'unknown'}-${index}`}>
                  <strong>{source.source || 'unknown document'}</strong>
                  {source.page ? `, page ${source.page}` : ''}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="settings-note">
          <p className="meta">
            Fine tuning happens in the Ingestion and Current Settings panels. Change the values there, then restart ingestion.
          </p>
        </section>
      </section>
    </main>
  );
}
