import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Settings, Plus, User, Loader2, BookOpen, Key, CheckCircle2, LogOut, Info, Scale, Gavel, LayoutGrid, Calendar, FileText, Globe, ArrowRight, Brain, Search, AlertTriangle, BrainCircuit } from 'lucide-react';
import { useAuthStore } from '../stores/authStore';
import { apiFetch } from '../config/api';
import { API_URL_OPTIONS, DEFAULT_LLM_API_URL } from '../config/api';
import { getApiSettings, saveApiSettings, type ApiSettings, type SearchProvider, type SearchEngine } from '../services/apiSettingsService';
import { fetchWithCache, getCachedValue, setCachedValue } from '../services/clientCache';
import CaseCard from '../components/CaseCard';
import { Case } from '../types/case';
import ThemeToggle from '../components/ThemeToggle';

export interface Notebook {
  id: string;
  title?: string;
  name?: string;
  author?: string;
  date?: string;
  sources?: number;
  image?: string;
  isFeatured?: boolean;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

export interface MonitoringStats {
  total_chunks: number;
  indexed_files: number;
  total_cases: number;
  ai_readiness: string;
}

const NOTEBOOK_LIST_CACHE_TTL_MS = 2 * 60 * 1000;

const Dashboard = ({ 
  onOpenNotebook, 
  onOpenCase, 
  onOpenScraper, 
  onOpenCalendar,
  onOpenReports,
  refreshTrigger = 0, 
  supabaseConfigured 
}: { 
  onOpenNotebook: (n: Notebook) => void; 
  onOpenCase: (c: Case) => void; 
  onOpenScraper?: () => void; 
  onOpenCalendar?: () => void;
  onOpenReports?: () => void;
  refreshTrigger?: number; 
  supabaseConfigured: boolean | null 
}) => {
  const { user, signOut } = useAuthStore();
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [cases, setCases] = useState<Case[]>([]);
  const [activeTab, setActiveTab] = useState<'cases' | 'notebooks'>('cases');
  const [loading, setLoading] = useState(true);
  
  // Notebook Modal
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [newNotebookName, setNewNotebookName] = useState('');
  
  // Case Modal
  const [caseModalOpen, setCaseModalOpen] = useState(false);
  const [newCaseData, setNewCaseData] = useState({
    case_number: '',
    case_year: new Date().getFullYear().toString(),
    case_title: '',
    primary_counsel: '',
    requester_department: '',
  });

  const [monitoringStats, setMonitoringStats] = useState<MonitoringStats | null>(null);
  const [loadingStats, setLoadingStats] = useState(true);

  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');
  const [configOpen, setConfigOpen] = useState(false);
  const [apiUrl, setApiUrl] = useState(DEFAULT_LLM_API_URL);
  const [apiKey, setApiKey] = useState('');
  const [searchProvider, setSearchProvider] = useState<SearchProvider>('serper');
  const [searchApiKey, setSearchApiKey] = useState('');
  const [searchEngine, setSearchEngine] = useState<SearchEngine>('google');
  const [configSaving, setConfigSaving] = useState(false);
  const [configSaved, setConfigSaved] = useState(false);

  const effectiveUserId = user?.id || 'local';
  const effectiveEmail = user?.email || '';
  const notebookListCacheKey = `notebooks:${effectiveUserId}:${effectiveEmail || 'anonymous'}`;

  useEffect(() => {
    const s = getApiSettings(effectiveUserId);
    if (s) {
      setApiUrl(s.apiUrl || DEFAULT_LLM_API_URL);
      setApiKey(s.apiKey || '');
      setSearchProvider((s.searchProvider as SearchProvider) || 'serper');
      setSearchApiKey(s.searchApiKey || '');
      setSearchEngine((s.searchEngine as SearchEngine) || 'google');
    }
  }, [effectiveUserId]);

  const handleSaveConfig = () => {
    setConfigSaving(true);
    setConfigSaved(false);
    const settings: ApiSettings = {
      apiUrl: apiUrl.trim(),
      apiKey: apiKey.trim(),
      searchProvider,
      searchApiKey: searchApiKey.trim(),
      searchEngine,
    };
    saveApiSettings(effectiveUserId, settings);
    setConfigSaved(true);
    setTimeout(() => {
      setConfigSaving(false);
      setConfigSaved(false);
    }, 1500);
  };

  const fetchNotebooks = async (options?: { force?: boolean }) => {
    const cached = getCachedValue<Notebook[]>(notebookListCacheKey);
    if (cached) {
      setNotebooks(cached);
      setLoading(false);
      if (!options?.force) return;
    } else {
      setLoading(true);
    }
    try {
      const list = await fetchWithCache<Notebook[]>(
        notebookListCacheKey,
        NOTEBOOK_LIST_CACHE_TTL_MS,
        async () => {
          const res = await apiFetch(`/api/v1/kb/notebooks?user_id=${encodeURIComponent(effectiveUserId)}&email=${encodeURIComponent(effectiveEmail)}`);
          const data = await res.json();
          if (!data?.success || !Array.isArray(data.notebooks)) return [];
          return data.notebooks.map((row: any) => ({
            id: row.id,
            title: row.name,
            name: row.name,
            description: row.description,
            created_at: row.created_at,
            updated_at: row.updated_at,
            date: row.updated_at ? new Date(row.updated_at).toLocaleDateString('en-US') : 'Just now',
            sources: typeof row.sources === 'number' ? row.sources : 0,
          }));
        },
        { force: options?.force, useStaleOnError: true }
      );
      setNotebooks(list);
    } catch (err) {
      console.error('Failed to fetch notebooks:', err);
      if (!cached) setNotebooks([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchCases = async (options?: { force?: boolean }) => {
    try {
      const res = await apiFetch('/api/v1/cases/');
      const data = await res.json();
      if (data?.success && Array.isArray(data.cases)) {
        setCases(data.cases);
      }
    } catch (err) {
      console.error('Failed to fetch cases:', err);
    }
  };

  const fetchMonitoringStats = async () => {
    setLoadingStats(true);
    try {
      const res = await apiFetch('/api/v1/cases/monitoring/stats');
      const data = await res.json();
      if (data?.success) {
        setMonitoringStats(data.portfolio_summary);
      }
    } catch (err) {
      console.error('Failed to fetch monitoring stats:', err);
    } finally {
      setLoadingStats(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchNotebooks({ force: refreshTrigger > 0 }),
      fetchCases({ force: refreshTrigger > 0 }),
      fetchMonitoringStats()
    ]).finally(() => setLoading(false));
  }, [effectiveUserId, refreshTrigger]);

  const handleDeleteNotebook = async (id: string) => {
    try {
      const res = await apiFetch(`/api/v1/kb/notebooks/${id}`, { method: 'DELETE' });
      const data = await res.json();
      if (!data.success) throw new Error(data.message || 'Notebook deletion failed');
      setNotebooks(prev => {
        const next = prev.filter(n => n.id !== id);
        setCachedValue(notebookListCacheKey, next, NOTEBOOK_LIST_CACHE_TTL_MS);
        return next;
      });
    } catch (err) {
      console.error('Failed to delete notebook:', err);
    }
  };

  const handleCreateNotebook = async () => {
    const name = newNotebookName.trim();
    if (!name) return;
    setCreating(true);
    setCreateError('');
    try {
      const res = await apiFetch('/api/v1/kb/notebooks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description: '', user_id: effectiveUserId, email: effectiveEmail }),
      });
      const data = await res.json();
      if (data?.success && data?.notebook) {
        const nb = data.notebook;
        const newNb: Notebook = {
          id: nb.id,
          title: nb.name,
          name: nb.name,
          description: nb.description,
          created_at: nb.created_at,
          updated_at: nb.updated_at,
          date: nb.updated_at ? new Date(nb.updated_at).toLocaleDateString('en-US') : 'Just now',
          sources: 0,
        };
        setNotebooks(prev => {
          const next = [newNb, ...prev.filter(item => item.id !== newNb.id)];
          setCachedValue(notebookListCacheKey, next, NOTEBOOK_LIST_CACHE_TTL_MS);
          return next;
        });
        setCreateModalOpen(false);
        setNewNotebookName('');
        onOpenNotebook(newNb);
      } else {
        setCreateError(data?.message || 'Create failed');
      }
    } catch (err: any) {
      setCreateError(err?.message || 'Create failed');
    } finally {
      setCreating(false);
    }
  };

  const handleCreateCase = async () => {
    const { case_number, case_year } = newCaseData;
    if (!case_number || !case_year) return;
    setCreating(true);
    setCreateError('');
    try {
      let case_no = case_number;
      if (case_no.includes('/')) {
        case_no = case_no.split('/')[0];
      }

      const res = await apiFetch('/api/v1/cases/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...newCaseData,
          case_number: case_no,
          auto_create_notebook: true
        }),
      });
      const data = await res.json();
      if (data?.success && data?.case) {
        setCases(prev => [data.case, ...prev]);
        setCaseModalOpen(false);
        setNewCaseData({
          case_number: '',
          case_year: new Date().getFullYear().toString(),
          case_title: '',
          primary_counsel: '',
          requester_department: '',
        });
      } else {
        setCreateError(data?.message || 'Failed to add case');
      }
    } catch (err: any) {
      setCreateError(err?.message || 'Failed to add case');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-8 transition-colors duration-500">
      <header className="sticky top-0 z-30 bg-[var(--surface-low)]/80 backdrop-blur-xl rounded-b-2xl -mx-6 px-6 py-4 mb-12 border-b border-[var(--border)] shadow-sm">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-[var(--accent)] rounded-xl flex items-center justify-center text-white shadow-lg rotate-3">
              <Scale size={24} />
            </div>
            <h1 className="text-2xl font-bold text-[var(--text-primary)] tracking-tight font-display">LawNidhi</h1>
          </div>
          <div className="flex items-center gap-4">
            <div className="hidden rounded-full border border-white/70 bg-white/60 px-3 py-1.5 text-sm text-ios-gray-700 shadow-ios-sm md:block">
              {user?.email || user?.id}
            </div>
            <motion.button
              whileTap={{ scale: 0.95 }}
              type="button"
              onClick={() => setConfigOpen((o) => !o)}
              className="text-ios-gray-600 hover:text-ios-gray-900 flex items-center gap-2 px-3 py-2 rounded-ios hover:bg-white/50 transition-colors"
            >
              <Settings size={20} />
              <span className="text-sm font-medium">API Settings</span>
            </motion.button>
            <motion.button
              whileTap={{ scale: 0.95 }}
              type="button"
              onClick={() => void signOut()}
              className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] flex items-center gap-2 px-3 py-2 rounded-xl hover:bg-[var(--surface-high)] transition-colors"
            >
              <LogOut size={18} />
              <span className="hidden lg:inline text-sm font-bold uppercase tracking-widest">Sign out</span>
            </motion.button>
            <div className="w-10 h-10 bg-[var(--surface-high)] dark:bg-neutral-800 rounded-full flex items-center justify-center text-[var(--text-secondary)] border border-[var(--border)] shadow-inner">
              <User size={20} />
            </div>
            <ThemeToggle />
          </div>
        </div>
      </header>
 

      {!supabaseConfigured && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-5 shadow-lg backdrop-blur-sm"
        >
          <div className="flex items-start gap-4">
            <Info size={20} className="text-amber-500 mt-1 flex-shrink-0" />
            <div className="flex-1">
              <h3 className="text-sm font-bold text-amber-500 mb-1 uppercase tracking-wider">Trial Mode Active</h3>
              <p className="text-sm text-[var(--text-secondary)] mb-3 leading-relaxed">
                You're using LawNidhi in trial mode. Configure Supabase to enable professional user authentication and persistent cloud storage.
              </p>
              <a
                href="https://supabase.com"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs font-bold text-amber-500 hover:text-amber-400 underline underline-offset-4"
              >
                Setup Enterprise Auth <ArrowRight size={14} />
              </a>
            </div>
          </div>
        </motion.div>
      )}

      {configOpen && (
        <section className="mb-12 p-8 bg-[var(--surface-low)] rounded-2xl border border-[var(--border)] shadow-2xl transition-all">
          <div className="flex items-center gap-3 mb-8">
             <Key size={20} className="text-[var(--accent)]" />
             <h3 className="text-lg font-bold text-[var(--text-primary)]">Intelligence Core Configuration</h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
            <div className="space-y-6">
              <div className="flex items-center gap-2 mb-2">
                <Brain size={16} className="text-[var(--text-muted)]" />
                <h4 className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest">LLM Reasoning Engine</h4>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="block text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1.5 px-1">Gateway URL</label>
                  <select
                    value={apiUrl}
                    onChange={(e) => setApiUrl(e.target.value)}
                    className="w-full px-4 py-3 bg-[var(--surface-high)] border border-[var(--border)] rounded-xl text-sm text-[var(--text-primary)] focus:ring-2 focus:ring-[var(--accent)]/30 focus:border-[var(--accent)] transition-all outline-none"
                  >
                    {[apiUrl, ...API_URL_OPTIONS].filter((v, i, a) => a.indexOf(v) === i).map((url: string) => (
                      <option key={url} value={url}>{url}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1.5 px-1">Access Token</label>
                  <input
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="sk-..."
                    className="w-full px-4 py-3 bg-[var(--surface-high)] border border-[var(--border)] rounded-xl text-sm text-[var(--text-primary)] focus:ring-2 focus:ring-[var(--accent)]/30 focus:border-[var(--accent)] transition-all outline-none"
                  />
                </div>
              </div>
            </div>
            <div className="space-y-6">
              <div className="flex items-center gap-2 mb-2">
                <Search size={16} className="text-[var(--text-muted)]" />
                <h4 className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest">Discovery Engine</h4>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="block text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1.5 px-1">Provider Service</label>
                  <select
                    value={searchProvider}
                    onChange={(e) => setSearchProvider(e.target.value as SearchProvider)}
                    className="w-full px-4 py-3 bg-[var(--surface-high)] border border-[var(--border)] rounded-xl text-sm text-[var(--text-primary)] focus:ring-2 focus:ring-[var(--accent)]/30 focus:border-[var(--accent)] transition-all outline-none"
                  >
                    <option value="serper">Serper (Native)</option>
                    <option value="serpapi">SerpAPI (Cloud)</option>
                    <option value="bocha">Bocha (Global)</option>
                  </select>
                </div>
                {(searchProvider === 'serpapi' || searchProvider === 'bocha') && (
                  <div>
                    <label className="block text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1.5 px-1">Service Key</label>
                    <input
                      type="password"
                      value={searchApiKey}
                      onChange={(e) => setSearchApiKey(e.target.value)}
                      placeholder={searchProvider === 'bocha' ? 'Bocha API Key' : 'SerpAPI Key'}
                      className="w-full px-4 py-3 bg-[var(--surface-high)] border border-[var(--border)] rounded-xl text-sm text-[var(--text-primary)] focus:ring-2 focus:ring-[var(--accent)]/30 focus:border-[var(--accent)] transition-all outline-none"
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
          <div className="mt-10 flex justify-end">
            <motion.button
              whileTap={{ scale: 0.97 }}
              type="button"
              onClick={handleSaveConfig}
              disabled={configSaving}
              className="px-8 py-3 bg-[var(--accent)] text-white rounded-xl hover:bg-[var(--accent-dark)] disabled:opacity-50 flex items-center gap-2 text-sm font-bold shadow-lg shadow-[var(--accent)]/30 transition-all"
            >
              {configSaving ? <Loader2 size={16} className="animate-spin" /> : configSaved ? <CheckCircle2 size={16} /> : <Key size={16} />}
              {configSaving ? 'Synchronizing...' : configSaved ? 'Config Secured' : 'Save Protocol'}
            </motion.button>
          </div>
        </section>
      )}

      {/* Litigation AI Monitor */}
      <section className="mb-8">
        <div className="bg-[var(--surface-high)] rounded-2xl border border-[var(--border)] p-6 shadow-sm overflow-hidden relative group">
           <div className="absolute top-0 right-0 w-32 h-32 bg-[var(--accent)]/5 rounded-full -mr-16 -mt-16 blur-3xl group-hover:bg-[var(--accent)]/10 transition-all duration-700" />
           <div className="flex flex-col md:flex-row items-center justify-between gap-6 relative z-10">
              <div className="flex items-center gap-4">
                 <div className="w-12 h-12 bg-[var(--accent-soft)] rounded-2xl flex items-center justify-center text-[var(--accent)]">
                    <BrainCircuit size={24} className="animate-pulse" />
                 </div>
                 <div>
                    <h2 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider">Portfolio AI Readiness</h2>
                    <p className="text-xs text-[var(--text-muted)]">Real-time litigation indexing monitor (Zero-Cost CPU Engine)</p>
                 </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-8 w-full md:w-auto">
                 <div className="text-center md:text-left">
                    <span className="block text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1">Knowledge Chunks</span>
                    <span className="text-xl font-bold text-[var(--text-primary)] font-display">
                       {loadingStats ? <Loader2 size={16} className="animate-spin" /> : monitoringStats?.total_chunks.toLocaleString() || '0'}
                    </span>
                 </div>
                 <div className="text-center md:text-left border-l border-[var(--border)] pl-8">
                    <span className="block text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1">Indexed Orders</span>
                    <span className="text-xl font-bold text-[var(--text-primary)] font-display">
                       {loadingStats ? <Loader2 size={16} className="animate-spin" /> : monitoringStats?.indexed_files || '0'}
                    </span>
                 </div>
                 <div className="text-center md:text-left border-l border-[var(--border)] pl-8">
                    <span className="block text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1">Portfolio Sync</span>
                    <span className="text-xl font-bold text-emerald-600 font-display">
                       {loadingStats ? <Loader2 size={16} className="animate-spin" /> : monitoringStats?.ai_readiness || '0/0 Ready'}
                    </span>
                 </div>
                 <div className="text-center md:text-left border-l border-[var(--border)] pl-8">
                    <span className="block text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1">Engine Status</span>
                    <span className="flex items-center gap-1.5 text-xs font-bold text-emerald-500 bg-emerald-50 px-2 py-1 rounded-full w-fit">
                       <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
                       STABLE (CPU)
                    </span>
                 </div>
              </div>
           </div>
        </div>
      </section>

      <section>
        <div className="mb-8 border-b border-neutral-200">
          <div className="flex gap-8">
            <button
               onClick={() => setActiveTab('cases')}
               className={`pb-4 text-sm font-bold uppercase tracking-widest transition-colors relative ${activeTab === 'cases' ? 'text-[var(--accent)]' : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'}`}
             >
               <div className="flex items-center gap-2">
                 <Gavel size={18} />
                 Case Portfolio
               </div>
               {activeTab === 'cases' && (
                 <motion.div layoutId="activeTab" className="absolute bottom-0 left-0 right-0 h-1 bg-[var(--accent)] rounded-full" />
               )}
             </button>
             <button
               onClick={() => setActiveTab('notebooks')}
               className={`pb-4 text-sm font-bold uppercase tracking-widest transition-colors relative ${activeTab === 'notebooks' ? 'text-[var(--accent)]' : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'}`}
             >
               <div className="flex items-center gap-2">
                 <LayoutGrid size={18} />
                 General AI Notebooks
               </div>
               {activeTab === 'notebooks' && (
                 <motion.div layoutId="activeTab" className="absolute bottom-0 left-0 right-0 h-1 bg-[var(--accent)] rounded-full" />
               )}
             </button>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12 text-ios-gray-500">
            <Loader2 className="w-6 h-6 animate-spin mr-2" />
            Loading profile...
          </div>
        ) : activeTab === 'cases' ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              className="cursor-pointer bg-[var(--surface-high)] dark:bg-neutral-900 rounded-2xl border-2 border-dashed border-[var(--border)] flex flex-col items-center justify-center gap-4 hover:border-[var(--accent)] hover:bg-[var(--accent-soft)] transition-all min-h-[280px] shadow-sm"
              onClick={() => setCaseModalOpen(true)}
            >
              <div className="w-14 h-14 bg-white dark:bg-neutral-800 rounded-2xl flex items-center justify-center shadow-md border border-[var(--border)]">
                <Plus size={28} className="text-[var(--accent)]" />
              </div>
              <div className="text-center">
                <span className="block font-semibold text-neutral-700">Add New Case</span>
                <span className="text-xs text-neutral-500">Create workspace from case metadata</span>
              </div>
            </motion.div>

            {cases.map((c) => (
              <CaseCard key={c.id} caseItem={c} onClick={onOpenCase} />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* New Notebook Card */}
            <motion.div
              whileHover={{ scale: 1.02, y: -4 }}
              whileTap={{ scale: 0.98 }}
              className="cursor-pointer bg-[var(--surface-high)] rounded-2xl border-2 border-dashed border-[var(--border)] aspect-[4/3] flex flex-col items-center justify-center gap-4 hover:border-[var(--accent)] transition-colors shadow-sm"
              onClick={() => setCreateModalOpen(true)}
            >
              <div className="w-12 h-12 bg-[var(--accent)]/10 rounded-xl flex items-center justify-center">
                <Plus size={24} className="text-[var(--accent)]" />
              </div>
              <span className="font-bold text-[var(--text-secondary)] text-sm uppercase tracking-widest">New notebook</span>
            </motion.div>

            {/* Notebook Cards */}
            {notebooks.map((nb) => (
              <motion.div
                key={nb.id}
                whileHover={{ scale: 1.02, y: -4 }}
                whileTap={{ scale: 0.98 }}
                className="cursor-pointer bg-[var(--surface-low)] rounded-2xl p-6 border border-[var(--border)] shadow-sm hover:border-[var(--accent)] transition-all aspect-[4/3] flex flex-col justify-between"
                onClick={() => onOpenNotebook(nb)}
              >
                <div className="flex justify-between items-start">
                  <div className="w-10 h-10 bg-amber-500/10 rounded-xl flex items-center justify-center text-amber-600">
                    <BookOpen size={20} />
                  </div>
                </div>
                <div>
                  <h3 className="font-bold text-[var(--text-primary)] line-clamp-2 mb-2">
                    {nb.title || nb.name || 'Untitled'}
                  </h3>
                  <p className="text-[var(--text-muted)] text-[10px] font-bold uppercase tracking-widest">
                    {nb.date || (nb.updated_at ? new Date(nb.updated_at).toLocaleDateString('en-US') : '')}
                    {typeof nb.sources === 'number' ? ` · ${nb.sources} sources` : ''}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </section>

      {/* Create Modal — iOS Sheet */}
      <AnimatePresence>
        {createModalOpen && (
          <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center" onClick={() => !creating && setCreateModalOpen(false)}>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 glass-dark"
            />
            <motion.div
              initial={{ y: 100, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 100, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              className="relative bg-white rounded-t-ios-2xl sm:rounded-ios-2xl p-6 w-full max-w-md shadow-ios-xl"
              onClick={e => e.stopPropagation()}
            >
              {/* iOS Drag Indicator */}
              <div className="flex justify-center mb-4 sm:hidden">
                <div className="w-9 h-1 rounded-full bg-ios-gray-300" />
              </div>
              <h3 className="text-lg font-bold text-[var(--text-primary)] mb-4">New Laboratory Workspace</h3>
              <input
                type="text"
                className="w-full border border-[var(--border)] bg-[var(--surface-high)] rounded-xl px-4 py-4 mb-4 text-sm text-[var(--text-primary)] focus:ring-2 focus:ring-[var(--accent)]/30 focus:border-[var(--accent)] transition-all outline-none"
                placeholder="Notebook name"
                value={newNotebookName}
                onChange={e => setNewNotebookName(e.target.value)}
              />
              {createError && <p className="text-rose-500 text-sm mb-4 font-bold">{createError}</p>}
              <div className="flex justify-end gap-2">
                <motion.button
                  whileTap={{ scale: 0.95 }}
                  className="px-5 py-2.5 text-ios-gray-600 hover:bg-ios-gray-100 rounded-ios font-medium text-sm transition-colors"
                  onClick={() => !creating && setCreateModalOpen(false)}
                  disabled={creating}
                >
                  Cancel
                </motion.button>
                <motion.button
                  whileTap={{ scale: 0.95 }}
                  className="px-5 py-2.5 bg-primary text-white rounded-ios hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2 font-medium text-sm shadow-ios-sm transition-colors"
                  onClick={handleCreateNotebook}
                  disabled={creating || !newNotebookName.trim()}
                >
                  {creating && <Loader2 className="w-4 h-4 animate-spin" />}
                  Create
                </motion.button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Case Modal — New Portfolio Entry */}
      <AnimatePresence>
        {caseModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => !creating && setCaseModalOpen(false)}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            />
            <motion.div
              initial={{ scale: 0.9, opacity: 0, y: 20 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.9, opacity: 0, y: 20 }}
              className="relative bg-[var(--surface-low)] w-full max-w-2xl rounded-3xl border border-[var(--border)] shadow-2xl p-8 overflow-hidden max-h-[90vh] overflow-y-auto"
            >
              <div className="flex items-center gap-4 mb-8">
                <div className="w-12 h-12 bg-[var(--accent)]/10 rounded-2xl flex items-center justify-center text-[var(--accent)]">
                  <Plus size={28} />
                </div>
                <div>
                  <h3 className="text-2xl font-bold text-[var(--text-primary)] font-display">New Case Workspace</h3>
                  <p className="text-xs text-[var(--text-muted)] mt-1 font-medium italic">Initialize a new legal portfolio and AI reasoning lab.</p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                {/* Case Identifier */}
                <div className="space-y-4">
                  <div>
                    <label className="block text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1.5 px-1">Case Number</label>
                    <input
                      type="text"
                      value={newCaseData.case_number}
                      onChange={e => {
                        const val = e.target.value.toUpperCase();
                        setNewCaseData(prev => {
                          const next = { ...prev, case_number: val };
                          if (val.includes('/')) {
                            const [no, yr] = val.split('/');
                            if (yr && yr.length === 4) {
                              next.case_year = yr;
                            }
                          }
                          return next;
                        });
                      }}
                      placeholder="e.g. 83/2025"
                      className="w-full px-4 py-3.5 bg-[var(--surface-high)] border border-[var(--border)] rounded-xl text-sm font-bold text-[var(--text-primary)] outline-none focus:ring-2 focus:ring-[var(--accent)]/30 transition-all"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1.5 px-1">Case Year</label>
                    <input
                      type="text"
                      value={newCaseData.case_year}
                      onChange={e => setNewCaseData({ ...newCaseData, case_year: e.target.value })}
                      placeholder="2025"
                      className="w-full px-4 py-3.5 bg-[var(--surface-high)] border border-[var(--border)] rounded-xl text-sm font-bold text-[var(--text-primary)] outline-none focus:ring-2 focus:ring-[var(--accent)]/30 transition-all"
                    />
                  </div>
                </div>

                {/* Case Details */}
                <div className="space-y-4">
                  <div>
                    <label className="block text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1.5 px-1">Case Title / Parties</label>
                    <input
                      type="text"
                      value={newCaseData.case_title}
                      onChange={e => setNewCaseData({ ...newCaseData, case_title: e.target.value })}
                      placeholder="e.g. People vs Environment"
                      className="w-full px-4 py-3.5 bg-[var(--surface-high)] border border-[var(--border)] rounded-xl text-sm text-[var(--text-primary)] outline-none focus:ring-2 focus:ring-[var(--accent)]/30 transition-all"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1.5 px-1">Primary Counsel</label>
                    <input
                      type="text"
                      value={newCaseData.primary_counsel}
                      onChange={e => setNewCaseData({ ...newCaseData, primary_counsel: e.target.value })}
                      placeholder="Counsel name"
                      className="w-full px-4 py-3.5 bg-[var(--surface-high)] border border-[var(--border)] rounded-xl text-sm text-[var(--text-primary)] outline-none focus:ring-2 focus:ring-[var(--accent)]/30 transition-all"
                    />
                  </div>
                </div>
              </div>

              {createError && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mb-6 p-4 bg-rose-50 border border-rose-100 rounded-xl text-rose-600 text-xs font-bold flex items-center gap-2">
                  <AlertTriangle size={14} />
                  {createError}
                </motion.div>
              )}

              <div className="flex justify-end gap-3 pt-4 border-t border-[var(--border)]">
                <button
                  type="button"
                  onClick={() => !creating && setCaseModalOpen(false)}
                  className="px-6 py-3 rounded-xl font-bold text-sm text-[var(--text-muted)] hover:bg-[var(--surface-high)] transition-colors"
                  disabled={creating}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleCreateCase}
                  disabled={creating || !newCaseData.case_number || !newCaseData.case_year}
                  className="px-8 py-3 bg-[var(--accent)] text-white rounded-xl font-bold text-sm shadow-xl shadow-[var(--accent)]/30 disabled:opacity-50 flex items-center gap-2 transition-all"
                >
                  {creating && <Loader2 size={18} className="animate-spin" />}
                  {creating ? 'Initializing...' : 'Create Case Workspace'}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default Dashboard;
