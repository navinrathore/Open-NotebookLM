import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  ChevronLeft, Scale, Calendar, User, Briefcase, 
  FileText, MessageSquare, ExternalLink, Download,
  Clock, Info, Shield, Hash, Send, Bot, User as UserIcon, Loader2,
  Sparkles, Brain, ChevronRight, Image as ImageIcon, BrainCircuit, Plus, ArrowRight, X, Upload
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
    try {
      const res = await apiFetch(`/api/v1/cases/${caseItem.case_number}/${caseItem.case_year}/documents`);
      const data = await res.json();
      if (data?.success) {
        setDocuments(data.documents || []);
      }
    } catch (err) {
      console.error('Failed to fetch documents:', err);
    } finally {
      setLoadingDocs(false);
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
          files: [],
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

  const uploadFiles = async (files: FileList) => {
    // Shared upload engine logic
    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const formData = new FormData();
        formData.append('file', file);
        formData.append('email', user?.email || 'local');
        formData.append('user_id', user?.id || 'local');
        formData.append('notebook_id', caseItem.notebook_id || '');

        try {
            await apiFetch('/api/v1/kb/upload', {
                method: 'POST',
                body: formData,
            });
        } catch (err) {
            console.error('File upload failed:', file.name, err);
        }
    }
    fetchDocuments();
    setShowUploadModal(false);
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
              <h2 className="text-xs font-bold text-neutral-400 uppercase tracking-wider flex items-center gap-2">
                <FileText size={14} />
                Order Chronology
              </h2>
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
                          <a 
                            href={doc.url} 
                            target="_blank" 
                            rel="noreferrer"
                            className="p-1.5 text-neutral-300 hover:text-accent-500 transition-colors"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <Download size={14} />
                          </a>
                        )}
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
                placeholder="Ask Counsel AI about this case file..."
                className="w-full bg-[var(--surface-high)] border border-[var(--border)] rounded-2xl px-6 py-4 pr-16 text-sm focus:ring-2 focus:ring-[var(--accent)]/20 focus:border-[var(--accent)] outline-none transition-all shadow-sm text-[var(--text-primary)]"
                value={inputMsg}
                onChange={e => setInputMsg(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSendMessage()}
                disabled={isChatLoading}
              />
              <button 
                className={`absolute right-3 top-1/2 -translate-y-1/2 p-2 rounded-xl transition-all ${inputMsg.trim() ? 'bg-[var(--accent)] text-white shadow-glow-accent' : 'bg-neutral-200 text-neutral-400'}`}
                onClick={handleSendMessage}
                disabled={!inputMsg.trim() || isChatLoading}
              >
                <Send size={18} />
              </button>
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

      {/* Upload Sources Modal */}
      <AnimatePresence>
        {showUploadModal && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setShowUploadModal(false)}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            />
            <motion.div
              initial={{ scale: 0.9, opacity: 0, y: 20 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.9, opacity: 0, y: 20 }}
              className="relative bg-[var(--surface-low)] w-full max-w-lg rounded-3xl border border-[var(--border)] shadow-2xl p-8"
            >
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h3 className="text-xl font-bold text-[var(--text-primary)]">Add Case Sources</h3>
                  <p className="text-xs text-[var(--text-muted)] mt-1">Upload relevant legal filings or research notes.</p>
                </div>
                <button onClick={() => setShowUploadModal(false)} className="p-2 hover:bg-[var(--surface-high)] rounded-full text-[var(--text-muted)]">
                  <X size={20} />
                </button>
              </div>

              <label className="flex flex-col items-center justify-center w-full h-48 border-2 border-dashed border-[var(--border)] rounded-2xl bg-[var(--surface-high)] hover:bg-[var(--accent-soft)] hover:border-[var(--accent)] transition-all cursor-pointer group">
                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                  <div className="w-12 h-12 bg-[var(--accent-soft)] rounded-xl flex items-center justify-center text-[var(--accent)] mb-4 group-hover:scale-110 transition-transform">
                    <Upload size={24} />
                  </div>
                  <p className="text-sm font-bold text-[var(--text-primary)]">Click or drag files to upload</p>
                  <p className="text-[10px] text-[var(--text-muted)] mt-1 uppercase tracking-widest font-bold">PDF, DOCX, MD, OR IMAGE</p>
                </div>
                <input
                  type="file"
                  className="hidden"
                  multiple
                  onChange={(e) => e.target.files && uploadFiles(e.target.files)}
                />
              </label>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default CaseDetailPage;
