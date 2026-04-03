import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  ChevronLeft, Scale, Calendar, User, Briefcase, 
  FileText, MessageSquare, ExternalLink, Download,
  Clock, Info, Shield, Hash, Send, Bot, User as UserIcon, Loader2,
  Sparkles, Brain, ChevronRight, Image as ImageIcon, BrainCircuit, Plus, ArrowRight, X, Upload, Globe, Type, MoreVertical, Trash2
} from 'lucide-react';
import { Case, CaseDocument } from '../types/case';
import { apiFetch } from '../config/api';
import { useAuthStore } from '../stores/authStore';
import ReactMarkdown from 'react-markdown';
import ThemeToggle from '../components/ThemeToggle';

interface CaseDetailPageProps {
  caseItem: Case;
  onBack: () => void;
}

const CaseDetailPage: React.FC<CaseDetailPageProps> = ({ caseItem, onBack }) => {
  const { user } = useAuthStore();
  const [documents, setDocuments] = useState<CaseDocument[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [chatMessages, setChatMessages] = useState<any[]>([]);
  const [inputMsg, setInputMsg] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [chatLoadingStage, setChatLoadingStage] = useState('Thinking...');
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [syncLoading, setSyncLoading] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [fileUploading, setFileUploading] = useState(false);
  // URL import state
  const [introduceUrl, setIntroduceUrl] = useState('');
  const [introduceUrlLoading, setIntroduceUrlLoading] = useState(false);
  const [introduceUrlError, setIntroduceUrlError] = useState('');
  const [introduceUrlSuccess, setIntroduceUrlSuccess] = useState('');
  // Text paste state
  const [introduceText, setIntroduceText] = useState('');
  const [introduceTextLoading, setIntroduceTextLoading] = useState(false);
  const [introduceTextError, setIntroduceTextError] = useState('');
  const [introduceTextSuccess, setIntroduceTextSuccess] = useState('');
  const [activeMenuDocId, setActiveMenuDocId] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<CaseDocument | null>(null);
  
  // Three-column layout state
  const [leftPanelWidth, setLeftPanelWidth] = useState(380);
  const [rightPanelWidth, setRightPanelWidth] = useState(320);
  const [isStudioOpen, setIsStudioOpen] = useState(false);
  const [activeTool, setActiveTool] = useState<string>('chat');
  const [resizing, setResizing] = useState<'left' | 'right' | null>(null);

  useEffect(() => {
    fetchDocuments();
    // Initialize chat with a welcome message
    setChatMessages([
      {
        role: 'assistant',
        content: `Welcome to the Case Workspace for **${caseItem.case_number}/${caseItem.case_year}**. I've analyzed the available filings and orders. How can I help you today?`,
        time: new Date().toLocaleTimeString()
      }
    ]);
  }, [caseItem]);

  const fetchDocuments = async () => {
    setLoadingDocs(true);
    const em = user?.email || user?.id || 'local';
    try {
      // 1. Fetch case-specific documents (Official orders/filings)
      const caseRes = await apiFetch(`/api/v1/cases/${caseItem.case_number}/${caseItem.case_year}/documents`);
      const caseData = await caseRes.json();
      const officialDocs: CaseDocument[] = caseData?.success ? (caseData.documents || []) : [];

      // 2. Fetch knowledge base documents (Added sources/URLs/Text)
      const params = new URLSearchParams({ email: em });
      if (caseItem.notebook_id) params.set('notebook_id', caseItem.notebook_id);
      
      const kbRes = await apiFetch(`/api/v1/kb/list?${params.toString()}`);
      let kbDocs: CaseDocument[] = [];
      if (kbRes.ok) {
        const kbData = await kbRes.json();
        const files = Array.isArray(kbData?.files) ? kbData.files : [];
        kbDocs = files.map((f: any) => {
          const filename = f.original_path ? f.original_path.split('/').pop() : (f.id || 'Source');
          
          // Resolve static URL from original_path if possible
          let resolvedUrl = f.url || '';
          if (!resolvedUrl && f.original_path) {
            const idx = f.original_path.indexOf('/outputs/');
            if (idx >= 0) {
              resolvedUrl = f.original_path.slice(idx);
            }
          }

          return {
            id: f.id,
            name: filename,
            url: resolvedUrl,
            local_path: f.original_path,
            type: f.file_type || 'upload',
            status: f.status === 'done' ? 'AI-Indexed & Ready' : (f.status || 'imported'),
            date: f.created_at ? new Date(f.created_at).toLocaleDateString() : 'Added Source'
          };
        });
      }

      // 3. Merge and deduplicate
      const merged = [...officialDocs];
      const existingPaths = new Set(officialDocs.map(d => d.local_path || d.url));

      kbDocs.forEach(kbDoc => {
        const path = kbDoc.local_path || kbDoc.url;
        if (path && !existingPaths.has(path)) {
          merged.push(kbDoc);
          existingPaths.add(path);
        }
      });

      // SYNC CONTROL: Prune selectedFiles (remove deleted/stale records)
      const mergedPaths = new Set(merged.map(d => d.local_path || d.url || d.name).filter(Boolean));
      setSelectedFiles(prev => prev.filter(p => mergedPaths.has(p)));

      // Auto-select new documents by default
      const currentDocPaths = new Set(documents.map(d => d.local_path || d.url));
      const newPaths: string[] = [];
      merged.forEach(doc => {
        const path = doc.local_path || doc.url || doc.name;
        if (path && !currentDocPaths.has(path)) {
           newPaths.push(path);
        }
      });

      if (newPaths.length > 0) {
        setSelectedFiles(prev => {
          const next = new Set([...prev, ...newPaths]);
          return Array.from(next);
        });
      }

      setDocuments(merged);
    } catch (err) {
      console.error('Failed to fetch documents:', err);
    } finally {
      setLoadingDocs(false);
    }
  };

  const handleDeleteSource = async (doc: CaseDocument) => {
    if (!doc.local_path && !doc.url && !doc.id) return;
    
    // Use the explicit manifest ID for vector deletion (most reliable for backend)
    // Fallback to local_path/url/name for physical file lookup or legacy records
    const fileId = doc.id || doc.local_path || doc.url || doc.name;
    
    try {
      setSyncLoading(true);
      // 1. Delete vectors from FAISS index and manifest
      await apiFetch('/api/v1/kb/delete-vector', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: fileId,
          notebook_id: caseItem.notebook_id,
          email: user?.email || user?.id || 'local',
          notebook_title: caseItem.case_title || caseItem.case_number || ''
        }),
      });

      // 2. Delete physical file (Form data expected by backend)
      if (doc.local_path) {
        const formData = new FormData();
        formData.append('storage_path', doc.local_path);
        await apiFetch('/api/v1/kb/delete', {
          method: 'DELETE',
          body: formData,
        });
      }

      // 3. Refresh list and clear selection
      await fetchDocuments();
      const selectionIdentifier = doc.local_path || doc.url || doc.name;
      setSelectedFiles(prev => prev.filter(f => f !== selectionIdentifier));
      setShowDeleteConfirm(null);
      setActiveMenuDocId(null);
    } catch (err) {
      console.error('Failed to delete source:', err);
    } finally {
      setSyncLoading(false);
    }
  };

  const handleSendMessage = async () => {
    if (!inputMsg.trim() || isChatLoading) return;

    const userMsg = { role: 'user', content: inputMsg, time: new Date().toLocaleTimeString() };
    setChatMessages(prev => [...prev, userMsg]);
    setInputMsg('');
    setIsChatLoading(true);

    try {
      // Correct fields for /kb/chat
      const res = await apiFetch('/api/v1/kb/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: inputMsg,
          files: selectedFiles,
          notebook_id: caseItem.notebook_id,
          email: user?.email || user?.id || 'local',
          history: chatMessages.map(m => ({ role: m.role, content: m.content }))
        }),
      });
      const data = await res.json();
      if (data?.answer) {
        setChatMessages(prev => [...prev, { 
          role: 'assistant', 
          content: data.answer, 
          time: new Date().toLocaleTimeString() 
        }]);
      }
    } catch (err) {
      console.error('Chat error:', err);
    } finally {
      setIsChatLoading(false);
    }
  };


  const handleSyncOrders = async () => {
    setSyncLoading(true);
    setChatLoadingStage('Analyzing NGT Portal...');
    try {
      // Direct call to automated discovery & ingestion engine
      const res = await apiFetch('/api/v1/scrapers/download-orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_number: caseItem.case_number,
          case_year: caseItem.case_year,
          download_all: true
        }),
      });
      const data = await res.json();
      
      if (data.captcha_required) {
         console.warn("Manual CAPTCHA required for sync.");
      }

      if (data.success) {
        fetchDocuments(); // Refresh chronology with the new orders
      }
    } catch (err) {
      console.error('Sync failed:', err);
    } finally {
      setSyncLoading(false);
      setChatLoadingStage('Thinking...');
    }
  };

  const uploadFiles = async (inputFiles: FileList | File[]) => {
    const uploadQueue = Array.from(inputFiles || []);
    if (!uploadQueue.length) return;
    setFileUploading(true);
    setShowUploadModal(false);
    let successCount = 0;
    for (const file of uploadQueue) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('email', user?.email || 'local');
        formData.append('user_id', user?.id || 'local');
        formData.append('notebook_id', caseItem.notebook_id || '');
        formData.append('notebook_title', caseItem.case_title || caseItem.case_number || '');
        try {
            const res = await apiFetch('/api/v1/kb/upload', {
                method: 'POST',
                body: formData,
            });
            if (res.ok) successCount++;
        } catch (err) {
            console.error('File upload failed:', file.name, err);
        }
    }
    setFileUploading(false);
    fetchDocuments();
  };

  const handleImportUrlAsSource = async () => {
    const url = introduceUrl.trim();
    if (!url) return;
    setIntroduceUrlLoading(true);
    setIntroduceUrlError('');
    setIntroduceUrlSuccess('');
    try {
      const res = await apiFetch('/api/v1/kb/import-url-as-source', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: user?.email || 'local',
          user_id: user?.id || 'local',
          notebook_id: caseItem.notebook_id || '',
          notebook_title: caseItem.case_title || caseItem.case_number || '',
          url,
        }),
      });
      const data = await res.json();
      if (res.ok && data?.success) {
        setIntroduceUrlSuccess(`Imported: ${data.filename || url}`);
        setIntroduceUrl('');
        fetchDocuments();
      } else {
        setIntroduceUrlError(data?.detail || 'Import failed');
      }
    } catch (err: any) {
      setIntroduceUrlError(err?.message || 'Import failed');
    } finally {
      setIntroduceUrlLoading(false);
    }
  };

  const handleAddTextSource = async () => {
    const text = introduceText.trim();
    if (!text) return;
    setIntroduceTextLoading(true);
    setIntroduceTextError('');
    setIntroduceTextSuccess('');
    try {
      const res = await apiFetch('/api/v1/kb/import-text-as-source', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: user?.email || 'local',
          user_id: user?.id || 'local',
          notebook_id: caseItem.notebook_id || '',
          notebook_title: caseItem.case_title || caseItem.case_number || '',
          text,
          title: 'Pasted Text',
        }),
      });
      const data = await res.json();
      if (res.ok && data?.success) {
        setIntroduceTextSuccess('Text saved as source');
        setIntroduceText('');
        fetchDocuments();
      } else {
        setIntroduceTextError(data?.detail || 'Save failed');
      }
    } catch (err: any) {
      setIntroduceTextError(err?.message || 'Save failed');
    } finally {
      setIntroduceTextLoading(false);
    }
  };

  const handleImportDocument = async (doc: CaseDocument) => {
    if (!doc.local_path || syncLoading) return;
    
    setSyncLoading(true);
    try {
      const res = await apiFetch(`/api/v1/cases/${caseItem.case_number}/${caseItem.case_year}/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_path: doc.local_path,
          type: doc.type || 'order'
        })
      });
      const data = await res.json();
      if (data?.success) {
        alert("Discovery Success: Document linked and AI-indexed for zero-cost discovery.");
        // Refresh documents list to reflect 'imported' status
        await fetchDocuments();
      } else {
        alert("Import Error: " + (data?.detail || "Unknown failure"));
      }
    } catch (err) {
      console.error('Import failed:', err);
      alert("System Error: Failed to communicate with discovery bridge.");
    } finally {
      setSyncLoading(false);
    }
  };

  // Draggable Panel Resize Logic
  useEffect(() => {
    if (resizing === null) return;
    const onMove = (e: MouseEvent) => {
      if (resizing === 'left') {
        setLeftPanelWidth(Math.min(500, Math.max(300, e.clientX)));
      } else if (resizing === 'right') {
        const w = window.innerWidth - e.clientX;
        setRightPanelWidth(Math.min(500, Math.max(250, w)));
      }
    };
    const onUp = () => setResizing(null);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [resizing]);

  return (
    <div className="flex flex-col h-screen bg-[var(--surface)] transition-colors duration-500 overflow-hidden">
      {/* Header */}
      <header className="bg-[var(--surface-low)] border-b border-[var(--border)] px-6 py-3 flex items-center justify-between sticky top-0 z-20 shadow-sm backdrop-blur-md">
        <div className="flex items-center gap-4">
          <button 
            onClick={onBack}
            className="p-2 hover:bg-neutral-100 rounded-full transition-colors text-neutral-500"
          >
            <ChevronLeft size={20} />
          </button>
          <div>
            <div className="flex items-center gap-2">
               <span className="text-xs font-bold text-[var(--accent)] bg-[var(--accent-soft)] px-2 py-0.5 rounded tracking-wider uppercase">
                 Case File
               </span>
               <h1 className="text-xl font-bold text-[var(--text-primary)] font-display">
                 {caseItem.case_number}/{caseItem.case_year}
               </h1>
            </div>
            <p className="text-sm text-[var(--text-secondary)] italic ml-0.5">
               {caseItem.case_title || 'Untitled Case'}
             </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex flex-col items-end mr-4">
            <span className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">Status</span>
            <span className="text-sm font-semibold text-emerald-600">{caseItem.status}</span>
          </div>
          <button className="bg-[var(--accent)] text-white px-4 py-2 rounded-xl text-sm font-bold hover:bg-[var(--accent-dark)] transition-all flex items-center gap-2 shadow-sm">
            <Shield size={16} />
            Manage
          </button>
          <ThemeToggle />
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden relative">
        {/* Left Sidebar: Metadata & Documents */}
        <aside 
          className="border-r border-[var(--border)] bg-[var(--surface-low)] overflow-y-auto flex flex-col transition-all duration-300 relative group"
          style={{ width: leftPanelWidth }}
        >
          {/* Metadata Section */}
          <div className="p-6 border-b border-neutral-100">
            <h2 className="text-xs font-bold text-neutral-400 uppercase tracking-wider mb-4 flex items-center gap-2">
              <Info size={14} />
              Case Metadata
            </h2>
            <div className="space-y-4">
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded bg-neutral-50 flex items-center justify-center text-neutral-400 shrink-0">
                  <User size={16} />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-neutral-400 uppercase tracking-tighter">Primary Counsel</label>
                  <p className="text-sm font-medium text-neutral-800">{caseItem.primary_counsel || 'N/A'}</p>
                </div>
              </div>
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded bg-neutral-50 flex items-center justify-center text-neutral-400 shrink-0">
                  <Briefcase size={16} />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-neutral-400 uppercase tracking-tighter">Department</label>
                  <p className="text-sm font-medium text-neutral-800">{caseItem.requester_department || 'General'}</p>
                </div>
              </div>
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded bg-neutral-50 flex items-center justify-center text-neutral-400 shrink-0">
                  <Hash size={16} />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-neutral-400 uppercase tracking-tighter">Diary Number</label>
                  <p className="text-sm font-medium text-neutral-800">{caseItem.diary_number || 'Pending'}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Documents Section */}
          <div className="flex-1 p-6">
            
            {/* Quick Actions for Legal Discovery */}
            <div className="grid grid-cols-1 gap-2 mb-6">
              <button 
                onClick={() => handleSyncOrders()}
                className="w-full flex items-center justify-between p-3 rounded-xl bg-[var(--accent)] text-white hover:bg-[var(--accent-dark)] transition-all shadow-glow-accent group"
              >
                <div className="flex items-center gap-3">
                   <div className="w-8 h-8 rounded-lg bg-white/20 flex items-center justify-center text-white">
                      <Download size={18} className="group-hover:animate-bounce" />
                   </div>
                   <div className="text-left">
                     <div className="text-xs font-bold uppercase tracking-wider">Sync Orders Now</div>
                     <p className="text-[9px] opacity-70">Fetch latest from NGT</p>
                   </div>
                </div>
                <ArrowRight size={16} className="opacity-0 group-hover:opacity-100 transition-all -translate-x-2 group-hover:translate-x-0" />
              </button>

              <div className="flex gap-2">
                <button 
                  onClick={() => setShowUploadModal(true)}
                  className="flex-1 flex items-center gap-2 p-3 rounded-xl bg-[var(--surface-high)] border border-[var(--border)] hover:border-[var(--accent)] text-[var(--accent)] transition-all group"
                >
                  <Plus size={16} className="group-hover:rotate-90 transition-transform" />
                  <span className="text-xs font-bold uppercase tracking-wider">Add Sources</span>
                </button>
                <button 
                  className="flex-1 flex items-center gap-2 p-3 rounded-xl bg-[var(--surface-high)] border border-[var(--border)] opacity-60 cursor-not-allowed text-[var(--text-muted)]"
                  title="Coming Soon: NGT Case Reports"
                >
                  <FileText size={16} />
                  <span className="text-xs font-bold uppercase tracking-wider">Reports</span>
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  className="w-4 h-4 rounded border-neutral-300 text-[var(--accent)] focus:ring-[var(--accent)] bg-[var(--surface)] transition-all cursor-pointer"
                  checked={selectedFiles.length === documents.filter(d => d.status !== 'available').length && documents.length > 0}
                  onChange={(e) => {
                    if (e.target.checked) {
                      const allReadyIds = documents
                        .filter(d => d.status !== 'available')
                        .map(d => d.local_path || d.url || d.name)
                        .filter(Boolean) as string[];
                      setSelectedFiles(allReadyIds);
                    } else {
                      setSelectedFiles([]);
                    }
                  }}
                />
                <h2 className="text-xs font-bold text-neutral-400 uppercase tracking-wider">
                  {selectedFiles.length > 0 ? `Selected ${selectedFiles.length} ` : 'Order Chronology'}
                </h2>
              </div>
              <span className="text-[10px] font-bold bg-neutral-100 text-neutral-500 px-2 py-0.5 rounded-full">
                {documents.length} Files
              </span>
            </div>

            {loadingDocs ? (
              <div className="flex flex-col items-center justify-center py-12 opacity-50">
                <Loader2 className="animate-spin mb-2" size={24} />
                <span className="text-xs font-medium">Scanning local files...</span>
              </div>
            ) : documents.length > 0 ? (
              <div className="space-y-3">
                {documents.map((doc, idx) => (
                    <div 
                      onClick={() => doc.url && window.open(doc.url, '_blank')}
                       className={`group p-3 border border-[var(--border)] rounded-xl hover:border-[var(--accent)] hover:bg-[var(--accent-soft)] transition-all ${doc.status === 'available' ? 'border-dashed opacity-80' : 'cursor-pointer'}`}
                     >
                       <div className="flex items-start gap-4">
                         <div className="pt-2">
                            <input 
                              type="checkbox"
                              className="w-4 h-4 rounded border-neutral-300 text-[var(--accent)] focus:ring-[var(--accent)] bg-[var(--surface)] transition-all cursor-pointer"
                              checked={selectedFiles.includes(doc.local_path || doc.url || doc.name)}
                              onChange={(e) => {
                                 const fileId = doc.local_path || doc.url || doc.name;
                                 if (e.target.checked) setSelectedFiles(prev => [...prev, fileId]);
                                 else setSelectedFiles(prev => prev.filter(f => f !== fileId));
                              }}
                              onClick={(e) => e.stopPropagation()}
                              disabled={doc.status === 'available'}
                              title={doc.status === 'available' ? 'Import document first' : 'Select for AI Context'}
                            />
                         </div>
                         <div className={`w-10 h-10 rounded-xl bg-[var(--surface-high)] dark:bg-neutral-800 flex items-center justify-center text-[var(--text-secondary)] group-hover:text-[var(--accent)] transition-all ${doc.status === 'available' ? 'animate-pulse text-amber-500' : ''}`}>
                           <FileText size={18} />
                         </div>
                         <div className="flex-1 overflow-hidden">
                           <h4 className="text-sm font-bold text-[var(--text-primary)] truncate">{doc.name}</h4>
                          <div className="flex items-center gap-2 mt-1">
                            {doc.status === 'available' ? (
                               <span className="text-[10px] font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded uppercase tracking-wider">
                                 Discovered - Add to Notebook
                               </span>
                            ) : (
                              <div className="flex items-center gap-2">
                                <span className="text-[10px] font-medium text-neutral-400 flex items-center gap-1">
                                  <Clock size={10} />
                                  {doc.date || 'Order/Filing'}
                                </span>
                                <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded uppercase tracking-wider border border-emerald-100">
                                  AI-Indexed & Ready
                                </span>
                              </div>
                            )}
                          </div>
                        </div>
                        
                        {/* Action Area: Sync (Official) or Menu (Added) */}
                        <div className="flex items-center gap-1">
                          {doc.status === 'available' ? (
                            <button 
                              onClick={(e) => { e.stopPropagation(); handleImportDocument(doc); }}
                              disabled={syncLoading}
                              className="p-2 bg-[var(--accent)] text-white rounded-lg hover:shadow-glow-accent transition-all flex items-center gap-2"
                              title="Import into AI Notebook"
                            >
                              {syncLoading ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                              <span className="text-[10px] font-bold uppercase tracking-widest hidden sm:inline">Add</span>
                            </button>
                          ) : (
                            <div className="relative">
                              <button 
                                onClick={(e) => { 
                                  e.stopPropagation(); 
                                  const id = doc.local_path || doc.url || doc.name;
                                  setActiveMenuDocId(activeMenuDocId === id ? null : id); 
                                }}
                                className="p-1.5 text-neutral-300 hover:text-accent-500 hover:bg-accent-50 rounded-lg transition-all"
                              >
                                <MoreVertical size={16} />
                              </button>
                              
                              <AnimatePresence>
                                {activeMenuDocId === (doc.local_path || doc.url || doc.name) && (
                                  <motion.div 
                                    initial={{ opacity: 0, scale: 0.95, y: -10 }}
                                    animate={{ opacity: 1, scale: 1, y: 0 }}
                                    exit={{ opacity: 0, scale: 0.95, y: -10 }}
                                    className="absolute right-0 top-full mt-1 w-36 bg-white border border-neutral-100 rounded-xl shadow-xl z-50 overflow-hidden"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <a 
                                      href={doc.url} 
                                      target="_blank" 
                                      rel="noreferrer"
                                      className="w-full flex items-center gap-2 px-3 py-2 text-[10px] font-bold text-neutral-600 hover:bg-neutral-50 transition-colors uppercase tracking-wider"
                                      onClick={() => setActiveMenuDocId(null)}
                                    >
                                      <Download size={12} />
                                      Download
                                    </a>
                                    
                                    {/* Only show delete for non-official sources as requested */}
                                    {doc.type !== 'order' && doc.type !== 'cause_list' && (
                                      <button 
                                        onClick={() => setShowDeleteConfirm(doc)}
                                        className="w-full flex items-center gap-2 px-3 py-2 text-[10px] font-bold text-red-600 hover:bg-red-50 transition-colors uppercase tracking-wider border-t border-neutral-50"
                                      >
                                        <Trash2 size={12} />
                                        Delete
                                      </button>
                                    )}
                                  </motion.div>
                                )}
                              </AnimatePresence>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12 border-2 border-dashed border-neutral-100 rounded-xl">
                <p className="text-sm text-neutral-400">No documents linked yet.</p>
                <button className="mt-2 text-xs font-bold text-accent-600 hover:text-accent-700 uppercase tracking-wider">
                  Sync Orders Now
                </button>
              </div>
            )}
          </div>
        </aside>

        {/* Global Delete Confirmation Dialog */}
        <AnimatePresence>
          {showDeleteConfirm && (
            <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
              <motion.div 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0 bg-black/40 backdrop-blur-sm"
                onClick={() => setShowDeleteConfirm(null)}
              />
              <motion.div 
                initial={{ opacity: 0, scale: 0.9, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.9, y: 20 }}
                className="relative w-full max-w-sm bg-white rounded-3xl p-8 shadow-2xl"
              >
                <div className="w-16 h-16 bg-red-50 text-red-600 rounded-2xl flex items-center justify-center mx-auto mb-6">
                  <Trash2 size={32} />
                </div>
                <h3 className="text-xl font-bold text-center text-neutral-900 mb-2">Delete Source?</h3>
                <p className="text-sm text-neutral-500 text-center mb-8">
                  This will permanently remove <span className="font-bold text-neutral-700">{showDeleteConfirm.name}</span> from your notebook and the Counsel AI index.
                </p>
                <div className="flex gap-3">
                  <button 
                    onClick={() => setShowDeleteConfirm(null)}
                    className="flex-1 py-3 px-4 rounded-xl border border-neutral-200 text-sm font-bold text-neutral-400 hover:bg-neutral-50 transition-all"
                  >
                    CANCEL
                  </button>
                  <button 
                    onClick={() => handleDeleteSource(showDeleteConfirm)}
                    disabled={syncLoading}
                    className="flex-1 py-3 px-4 rounded-xl bg-red-600 text-white text-sm font-bold hover:bg-red-700 transition-all shadow-lg shadow-red-200 flex items-center justify-center gap-2"
                  >
                    {syncLoading ? <Loader2 size={16} className="animate-spin" /> : 'DELETE'}
                  </button>
                </div>
              </motion.div>
            </div>
          )}
        </AnimatePresence>

        {/* Resizer Left */}
        <div 
          className="w-1 hover:bg-[var(--accent)] cursor-col-resize z-10 transition-colors"
          onMouseDown={(e) => {
            setResizing('left');
          }}
        />
        
        {/* Center Panel: AI Conversation Lab */}
        <main className="flex-1 flex flex-col bg-[var(--surface)] relative overflow-hidden">
          {/* Chat Messages */}
          <div className="flex-1 overflow-y-auto p-8 space-y-6">
            {chatMessages.map((msg, idx) => (
              <div key={idx} className={`flex gap-4 ${msg.role === 'assistant' ? 'max-w-[85%]' : 'max-w-[70%] ml-auto flex-row-reverse'}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${msg.role === 'assistant' ? 'bg-[var(--accent-soft)] text-[var(--accent)]' : 'bg-neutral-800 text-white shadow-lg'}`}>
                  {msg.role === 'assistant' ? <Bot size={18} /> : <UserIcon size={18} />}
                </div>
                <div className={`p-4 rounded-2xl text-sm leading-relaxed shadow-sm ${msg.role === 'assistant' ? 'bg-[var(--surface-high)] text-[var(--text-primary)] border border-[var(--border)]' : 'bg-[var(--accent)] text-white'}`}>
                  <ReactMarkdown className="prose prose-sm max-w-none dark:prose-invert">
                    {msg.content}
                  </ReactMarkdown>
                  {msg.time && (
                    <span className={`text-[10px] mt-2 block ${msg.role === 'assistant' ? 'text-[var(--text-muted)]' : 'text-white/60'}`}>
                      {msg.time}
                    </span>
                  )}
                </div>
              </div>
            ))}
            {isChatLoading && (
              <div className="flex gap-4 max-w-[85%]">
                <div className="w-8 h-8 rounded-full bg-[var(--accent-soft)] text-[var(--accent)] flex items-center justify-center">
                  <Bot size={18} />
                </div>
                <div className="bg-[var(--surface-high)] px-4 py-3 rounded-2xl shadow-sm italic text-sm text-[var(--text-muted)] flex items-center gap-2 border border-[var(--border)]">
                  <Loader2 size={14} className="animate-spin" />
                  {chatLoadingStage}
                </div>
              </div>
            )}
          </div>

          {/* Chat Input */}
          <div className="p-6 bg-[var(--surface-low)] border-t border-[var(--border)]">
            <div className="max-w-4xl mx-auto relative group">
              <div className="absolute -top-10 left-0 right-0 flex justify-center gap-2 mb-2 pointer-events-auto">
                 <button onClick={() => setIsStudioOpen(!isStudioOpen)} className="px-3 py-1 bg-[var(--surface-high)] border border-[var(--border)] rounded-full text-[10px] font-bold text-[var(--text-muted)] hover:text-[var(--accent)] transition-all shadow-sm flex items-center gap-1.5 grow-0">
                    <Sparkles size={12} className={isStudioOpen ? 'text-[var(--accent)]' : ''} />
                    {isStudioOpen ? 'HIDE STUDIO' : 'SHOW STUDIO TOOLS'}
                 </button>
              </div>
              <input 
                type="text"
                placeholder={selectedFiles.length > 0 ? "Ask Counsel AI about this case file..." : "Please select files for context..."}
                className="w-full bg-[var(--surface-high)] border border-[var(--border)] rounded-2xl px-6 py-4 pr-32 text-sm focus:ring-2 focus:ring-[var(--accent)]/20 focus:border-[var(--accent)] outline-none transition-all shadow-sm text-[var(--text-primary)]"
                value={inputMsg}
                onChange={e => setInputMsg(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSendMessage()}
                disabled={isChatLoading || selectedFiles.length === 0}
              />
              <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-3">
                <span className="hidden sm:inline text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest leading-none">
                  {selectedFiles.length} sources
                </span>
                <button 
                  className={`p-2 rounded-xl transition-all ${inputMsg.trim() && selectedFiles.length > 0 ? 'bg-[var(--accent)] text-white shadow-glow-accent' : 'bg-neutral-200 text-neutral-400 opacity-50 cursor-not-allowed'}`}
                  onClick={handleSendMessage}
                  disabled={!inputMsg.trim() || isChatLoading || selectedFiles.length === 0}
                >
                  <Send size={18} />
                </button>
              </div>
            </div>
          </div>
        </main>

        {/* Resizer Right */}
        {isStudioOpen && (
          <div 
            className="w-1 hover:bg-[var(--accent)] cursor-col-resize z-10 transition-colors"
            onMouseDown={(e) => {
              setResizing('right');
            }}
          />
        )}

        {/* Right Sidebar: Studio Workspace */}
        <AnimatePresence>
          {isStudioOpen && (
            <motion.aside
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: rightPanelWidth, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              className="border-l border-[var(--border)] bg-[var(--surface-low)] flex flex-col overflow-hidden"
            >
              <div className="p-6 border-b border-[var(--border)] flex items-center justify-between">
                <h2 className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider flex items-center gap-2">
                  <Brain size={14} className="text-[var(--accent)]" />
                  Studio Workspace
                </h2>
                <button onClick={() => setIsStudioOpen(false)} className="p-1 hover:bg-[var(--surface-high)] rounded-md text-[var(--text-muted)]">
                   <ChevronRight size={16} />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                 {/* Studio Tools Mockup */}
                 {[
                   { icon: <ImageIcon className="text-orange-500" />, label: 'PPT Generator' },
                   { icon: <BrainCircuit className="text-purple-500" />, label: 'Case Mind Map' },
                   { icon: <Scale className="text-blue-500" />, label: 'Legal Quiz' },
                   { icon: <FileText className="text-green-500" />, label: 'Case Summary' }
                 ].map((tool, i) => (
                   <button key={i} className="w-full p-4 rounded-2xl bg-[var(--surface-high)] border border-[var(--border)] hover:border-[var(--accent)] transition-all text-left flex items-center gap-4 group">
                      <div className="w-10 h-10 rounded-xl bg-[var(--surface)] flex items-center justify-center group-hover:scale-110 transition-transform shadow-sm">
                        {tool.icon}
                      </div>
                      <div>
                        <div className="text-sm font-bold text-[var(--text-primary)]">{tool.label}</div>
                        <div className="text-[10px] text-[var(--text-muted)] font-medium">Generate AI insights</div>
                      </div>
                   </button>
                 ))}
                 
                 <div className="mt-8 p-6 rounded-2xl bg-gradient-to-br from-[var(--accent)]/10 to-indigo-500/10 border border-[var(--accent)]/20">
                    <p className="text-xs font-bold text-[var(--accent)] uppercase tracking-widest mb-2">Pro Tip</p>
                    <p className="text-xs text-[var(--text-secondary)] leading-relaxed italic">The Studio uses the latest rulings in your Order Chronology to generate mind maps and briefing slides.</p>
                 </div>
              </div>
            </motion.aside>
          )}
        </AnimatePresence>
      </div>

      {/* Add Sources Modal — Unified with General Notebook */}
      <AnimatePresence>
        {showUploadModal && (
          <div
            className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center"
            onClick={() => setShowUploadModal(false)}
          >
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            />
            <motion.div
              initial={{ y: 100, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 100, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              className="relative bg-[var(--surface-low)] rounded-t-3xl sm:rounded-3xl shadow-2xl border border-[var(--border)] w-full max-w-lg max-h-[90vh] overflow-hidden flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)] shrink-0">
                <h2 className="text-base font-semibold text-[var(--text-primary)] text-center flex-1">
                  Add source: Upload files, paste URL or text
                </h2>
                <button
                  onClick={() => setShowUploadModal(false)}
                  className="p-2 hover:bg-[var(--surface-high)] rounded-xl text-[var(--text-muted)]"
                >
                  <X size={20} />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-6 space-y-5">
                {/* 1. Upload files */}
                <div>
                  <p className="text-xs font-medium text-[var(--text-secondary)] mb-2 flex items-center gap-2">
                    <Upload size={14} /> Upload files
                  </p>
                  <label
                    className={`flex flex-col items-center justify-center gap-3 w-full min-h-[148px] py-5 px-4 rounded-2xl border-2 border-dashed transition-colors ${
                      fileUploading
                        ? 'border-blue-200 bg-blue-50/70 cursor-wait'
                        : 'border-[var(--border)] bg-[var(--surface-high)] hover:bg-[var(--accent-soft)] hover:border-[var(--accent)] cursor-pointer'
                    }`}
                    onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
                    onDrop={(e) => {
                      e.preventDefault();
                      if (e.dataTransfer.files?.length) {
                        uploadFiles(e.dataTransfer.files);
                      }
                    }}
                  >
                    <div className="w-12 h-12 rounded-2xl bg-[var(--accent-soft)] border border-[var(--border)] flex items-center justify-center shadow-sm">
                      {fileUploading ? <Loader2 size={22} className="animate-spin text-[var(--accent)]" /> : <Upload size={22} className="text-[var(--accent)]" />}
                    </div>
                    <div className="text-center">
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        {fileUploading ? 'Processing...' : 'Click or drag files here'}
                      </p>
                      <p className="text-xs text-[var(--text-muted)] mt-1">
                        PDF, DOCX, MD, Images · Supports multiple files
                      </p>
                    </div>
                    <input
                      type="file"
                      className="hidden"
                      multiple
                      accept=".pdf,.docx,.pptx,.png,.jpg,.jpeg,.mp4,.md"
                      onChange={(e) => {
                        if (e.target.files?.length) {
                          uploadFiles(e.target.files);
                          e.target.value = '';
                        }
                      }}
                    />
                  </label>
                </div>

                {/* 2. Website URL import */}
                <div className="border-t border-[var(--border)] pt-5">
                  <p className="text-xs font-medium text-[var(--text-secondary)] mb-2 flex items-center gap-2">
                    <Globe size={14} /> Website
                  </p>
                  <div className="flex gap-2">
                    <input
                      type="url"
                      value={introduceUrl}
                      onChange={(e) => { setIntroduceUrl(e.target.value); setIntroduceUrlError(''); setIntroduceUrlSuccess(''); }}
                      placeholder="https://..."
                      className="flex-1 px-3 py-2 border border-[var(--border)] rounded-xl text-sm outline-none focus:ring-2 focus:ring-[var(--accent)] bg-[var(--surface-high)] text-[var(--text-primary)]"
                    />
                    <button
                      type="button"
                      onClick={handleImportUrlAsSource}
                      disabled={introduceUrlLoading || !introduceUrl.trim()}
                      className="px-4 py-2 rounded-xl bg-[var(--accent)] text-white text-sm font-medium hover:opacity-90 disabled:opacity-50 shrink-0 flex items-center gap-2"
                    >
                      {introduceUrlLoading ? 'Parsing...' : 'Parse URL'}
                    </button>
                  </div>
                  {introduceUrlError && <p className="text-xs text-red-500 mt-1">{introduceUrlError}</p>}
                  {introduceUrlSuccess && <p className="text-xs text-green-600 mt-1">{introduceUrlSuccess}</p>}
                  <p className="text-xs text-[var(--text-muted)] mt-1">Extracts text from URL and indexes it</p>
                </div>

                {/* 3. Paste text */}
                <div className="border-t border-[var(--border)] pt-5">
                  <p className="text-xs font-medium text-[var(--text-secondary)] mb-2 flex items-center gap-2">
                    <Type size={14} /> Paste text
                  </p>
                  <textarea
                    value={introduceText}
                    onChange={(e) => { setIntroduceText(e.target.value); setIntroduceTextError(''); setIntroduceTextSuccess(''); }}
                    placeholder="Paste text here..."
                    rows={4}
                    className="w-full px-3 py-2 border border-[var(--border)] rounded-xl text-sm outline-none focus:ring-2 focus:ring-[var(--accent)] resize-none bg-[var(--surface-high)] text-[var(--text-primary)]"
                  />
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-xs text-[var(--text-muted)]">Added as .md source</span>
                    <button
                      type="button"
                      onClick={handleAddTextSource}
                      disabled={introduceTextLoading || !introduceText.trim()}
                      className="px-4 py-2 rounded-xl bg-neutral-800 text-white text-sm font-medium hover:bg-neutral-900 disabled:opacity-50 flex items-center gap-2"
                    >
                      {introduceTextLoading ? 'Saving...' : 'Save'}
                    </button>
                  </div>
                  {introduceTextError && <p className="text-xs text-red-500 mt-1">{introduceTextError}</p>}
                  {introduceTextSuccess && <p className="text-xs text-green-600 mt-1">{introduceTextSuccess}</p>}
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default CaseDetailPage;
