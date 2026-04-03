/**
 * LawNidhi Integration — Scraper Control Page
 *
 * Dedicated page for managing NGT scrapers:
 * - Sync cause lists (trigger from UI)
 * - Search cases (with CAPTCHA solving feedback)
 * - Download orders (with auto-import to notebook)
 * - View scraper status and recent activity
 *
 * All LawNidhi-specific frontend code is in separate files/directories.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ChevronLeft, RefreshCw, Search, Download, Activity,
  FileText, CheckCircle2, XCircle, Loader2, Clock,
  AlertTriangle, Database, Calendar, ArrowRight, Zap,
  Globe, Scale
} from 'lucide-react';
import { apiFetch } from '../config/api';
import ThemeToggle from '../components/ThemeToggle';

// ----------- Types -----------

interface ScraperStatus {
  db_stats: Record<string, number>;
  latest_schedule: {
    schedule_date: string;
    court_no: string;
    judge_name: string;
    list_type: string;
    case_count: number;
  } | null;
  total_schedules: number;
}

interface OrderResult {
  order_date: string;
  suggested_filename: string;
  url?: string;
}

interface SearchResult {
  success: boolean;
  diary_number: string;
  orders: OrderResult[];
  total_orders: number;
  message?: string;
  captcha_required?: boolean;
  captcha_image?: string;
}

interface SyncResult {
  success: boolean;
  processed: number;
  message: string;
}

interface DownloadResult {
  success: boolean;
  downloaded: string[];
  imported_to_notebook: string[];
  total_downloaded: number;
  message: string;
}

type ActivityLogItem = {
  id: string;
  type: 'sync' | 'search' | 'download' | 'error';
  message: string;
  timestamp: string;
  details?: string;
};

// ----------- Component -----------

const ScraperPage = ({ onBack }: { onBack: () => void }) => {
  // Status
  const [status, setStatus] = useState<ScraperStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);

  // Sync
  const [syncing, setSyncing] = useState(false);
  const [syncDate, setSyncDate] = useState('');
  const [showAdvancedSync, setShowAdvancedSync] = useState(false);

  // Search
  const [searchCaseNo, setSearchCaseNo] = useState('');
  const [searchCaseYear, setSearchCaseYear] = useState(() => {
    const now = new Date();
    const year = now.getFullYear();
    return now.getMonth() < 2 ? (year - 1).toString() : year.toString();
  });
  const [searching, setSearching] = useState(false);
  const [searchResult, setSearchResult] = useState<SearchResult | null>(null);

  // Download
  const [downloading, setDownloading] = useState(false);
  const [downloadResult, setDownloadResult] = useState<DownloadResult | null>(null);

  // Activity log
  const [activityLog, setActivityLog] = useState<ActivityLogItem[]>([]);

  // Manual CAPTCHA Fallback
  const [captchaModalOpen, setCaptchaModalOpen] = useState(false);
  const [captchaImage, setCaptchaImage] = useState('');
  const [manualCaptchaText, setManualCaptchaText] = useState('');
  const [isSubmittingManual, setIsSubmittingManual] = useState(false);

  // Progress Feedback
  const [searchStatus, setSearchStatus] = useState<string>('');

  const addLog = useCallback((type: ActivityLogItem['type'], message: string, details?: string) => {
    setActivityLog((prev) => [
      {
        id: `${Date.now()}-${Math.random()}`,
        type,
        message,
        timestamp: new Date().toLocaleTimeString(),
        details,
      },
      ...prev.slice(0, 49), // Keep last 50 items
    ]);
  }, []);

  // Fetch status on load
  useEffect(() => {
    fetchStatus();
  }, []);

  const fetchStatus = async () => {
    setStatusLoading(true);
    try {
      const res = await apiFetch('/api/v1/scrapers/status');
      const data = await res.json();
      if (data.success) {
        setStatus(data);
      }
    } catch (err) {
      console.error('Failed to fetch scraper status:', err);
    } finally {
      setStatusLoading(false);
    }
  };

  // --- Sync Cause Lists ---
  const handleSync = async () => {
    setSyncing(true);
    addLog('sync', 'Starting cause list sync...');
    try {
      const body: any = {};
      if (syncDate) body.start_date = syncDate;
      const res = await apiFetch('/api/v1/scrapers/sync-cause-lists', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data: SyncResult = await res.json();
      if (data.success) {
        addLog('sync', `✓ ${data.message}`, `Processed ${data.processed} cause list(s)`);
        fetchStatus(); // Refresh status
      } else {
        addLog('error', 'Sync failed', data.message);
      }
    } catch (err: any) {
      addLog('error', 'Sync error', err?.message || 'Unknown error');
    } finally {
      setSyncing(false);
    }
  };

  // --- Search Case ---
  const handleSearch = async () => {
    if (!searchCaseNo.trim()) return;

    let caseNo = searchCaseNo.trim();
    let caseYear = searchCaseYear.trim();

    // Support "83/2025" format
    if (caseNo.includes('/')) {
      const parts = caseNo.split('/');
      caseNo = parts[0];
      caseYear = parts[1] || caseYear;
    }

    if (!caseYear) {
      addLog('error', 'Case year is required');
      return;
    }

    setSearching(true);
    setSearchResult(null);
    setSearchStatus('Solving CAPTCHA (Automated)...');
    addLog('search', `Searching case ${caseNo}/${caseYear}...`);

    try {
      const res = await apiFetch('/api/v1/scrapers/search-case', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_number: caseNo,
          case_year: caseYear,
        }),
      });
      const data: SearchResult = await res.json();
      
      if (data.captcha_required) {
        setCaptchaImage(data.captcha_image || '');
        setCaptchaModalOpen(true);
        setSearchStatus('Manual verification required.');
        return;
      }

      setSearchResult(data);
      if (data.success) {
        setSearchStatus('Search completed.');
        addLog('search', `✓ Found diary: ${data.diary_number}, ${data.total_orders} order(s)`, `Case ${caseNo}/${caseYear}`);
      } else {
        setSearchStatus('Search failed.');
        addLog('error', data.message || 'Search failed');
      }
    } catch (err: any) {
      setSearchStatus('Error occurred.');
      addLog('error', 'Search error', err?.message || 'Unknown error');
    } finally {
      setSearching(false);
    }
  };

  const handleManualCaptchaSubmit = async () => {
    if (!manualCaptchaText.trim()) return;
    setIsSubmittingManual(true);
    setSearchStatus('Verifying manual entry...');

    try {
      const res = await apiFetch('/api/v1/scrapers/solve-manual-captcha', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_number: searchCaseNo,
          case_year: searchCaseYear,
          captcha_text: manualCaptchaText,
        }),
      });
      const data: SearchResult = await res.json();
      setSearchResult(data);
      if (data.success) {
        setCaptchaModalOpen(false);
        setManualCaptchaText('');
        setSearchStatus('Search completed.');
        addLog('search', `✓ Manual verification success: ${data.diary_number}`, `Case ${searchCaseNo}/${searchCaseYear}`);
      } else {
        setSearchStatus('Verification failed.');
        addLog('error', data.message || 'Manual verification failed');
      }
    } catch (err: any) {
      setSearchStatus('Error during verification.');
      addLog('error', 'Verification error', err?.message || 'Unknown error');
    } finally {
      setIsSubmittingManual(false);
    }
  };

  // --- Download Orders ---
  const handleDownloadOrders = async () => {
    if (!searchCaseNo.trim()) return;

    let caseNo = searchCaseNo.trim();
    let caseYear = searchCaseYear.trim();
    if (caseNo.includes('/')) {
      const parts = caseNo.split('/');
      caseNo = parts[0];
      caseYear = parts[1] || caseYear;
    }

    setDownloading(true);
    setDownloadResult(null);
    addLog('download', `Downloading orders for ${caseNo}/${caseYear}...`);

    try {
      const res = await apiFetch('/api/v1/scrapers/download-orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_number: caseNo,
          case_year: caseYear,
          download_all: true,
        }),
      });
      const data: DownloadResult = await res.json();
      setDownloadResult(data);
      if (data.success) {
        addLog('download', `✓ ${data.message}`, `${data.imported_to_notebook?.length || 0} imported to notebook`);
        fetchStatus();
      } else {
        addLog('error', data.message || 'Download failed');
      }
    } catch (err: any) {
      addLog('error', 'Download error', err?.message || 'Unknown error');
    } finally {
      setDownloading(false);
    }
  };

  // --- Parse "83/2025" input ---
  const handleCaseInput = (val: string) => {
    setSearchCaseNo(val);
    if (val.includes('/')) {
      const parts = val.split('/');
      if (parts[1]) setSearchCaseYear(parts[1]);
    }
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-8 min-h-screen transition-colors duration-500">
      {/* Header */}
      <header className="mb-10">
        <div className="flex items-center justify-between gap-4 mb-8">
          <div className="flex items-center gap-4">
            <motion.button
              whileTap={{ scale: 0.95 }}
              onClick={onBack}
              className="p-2.5 rounded-xl hover:bg-[var(--surface-high)] transition-colors text-[var(--text-secondary)] border border-[var(--border)] shadow-sm bg-[var(--surface-low)]"
            >
              <ChevronLeft size={20} />
            </motion.button>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-amber-400 to-orange-600 rounded-xl flex items-center justify-center shadow-lg rotate-3">
                <Scale size={24} className="text-white" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-[var(--text-primary)] tracking-tight font-display">Scraper Control</h1>
                <p className="text-[var(--text-secondary)] font-medium mt-1">NGT Court — Cause Lists, Orders & Reports</p>
              </div>
            </div>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Left Column: Controls - Span 2 on Desktop/iPad */}
        <div className="md:col-span-2 space-y-6">

          {/* Status Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 }}
              className="bg-[var(--surface-low)] rounded-2xl border border-[var(--border)] p-6 shadow-sm flex flex-col justify-between"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-emerald-50 dark:bg-emerald-900/20 flex items-center justify-center">
                  <Database size={20} className="text-emerald-600 dark:text-emerald-400" />
                </div>
                <span className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest">Schedules</span>
              </div>
              <p className="text-2xl font-bold text-[var(--text-primary)] leading-none">
                {statusLoading ? '—' : status?.total_schedules || 0}
              </p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="bg-[var(--surface-low)] rounded-2xl border border-[var(--border)] p-6 shadow-sm flex flex-col justify-between"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-900/20 flex items-center justify-center">
                  <Calendar size={20} className="text-blue-600 dark:text-blue-400" />
                </div>
                <span className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest">Last Sync</span>
              </div>
              <p className="text-sm font-bold text-[var(--text-primary)] truncate">
                {statusLoading ? '—' : status?.latest_schedule?.schedule_date || 'Never'}
              </p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 }}
              className="bg-[var(--surface-low)] rounded-2xl border border-[var(--border)] p-6 shadow-sm flex flex-col justify-between"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-purple-50 dark:bg-purple-900/20 flex items-center justify-center">
                  <FileText size={20} className="text-purple-600 dark:text-purple-400" />
                </div>
                <span className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest">DB Records</span>
              </div>
              <p className="text-2xl font-bold text-[var(--text-primary)] leading-none">
                {statusLoading ? '—' : Object.values(status?.db_stats || {}).reduce((a, b) => a + b, 0)}
              </p>
            </motion.div>
          </div>

          {/* Sync Cause Lists */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="bg-[var(--surface-low)] rounded-3xl border border-[var(--border)] p-8 shadow-xl"
          >
            <div className="flex items-center justify-between mb-8">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-2xl bg-amber-50 dark:bg-amber-900/20 flex items-center justify-center">
                  <RefreshCw size={24} className="text-amber-600 dark:text-amber-400" />
                </div>
                <div>
                  <h3 className="text-xl font-bold text-[var(--text-primary)]">Sync Cause Lists</h3>
                  <p className="text-sm text-[var(--text-secondary)]">Scan NGT website → Download → Parse → Ingest</p>
                </div>
              </div>
            </div>
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <motion.button
                  whileTap={{ scale: 0.97 }}
                  className="px-8 py-3.5 bg-amber-500 hover:bg-amber-600 text-white rounded-2xl font-bold text-sm shadow-xl shadow-amber-500/20 disabled:opacity-50 flex items-center gap-3 transition-all"
                >
                  {syncing ? <Loader2 size={18} className="animate-spin" /> : <Zap size={18} />}
                  {syncing ? 'Syncing...' : 'Sync Recent Activity'}
                </motion.button>
                
                <button 
                  onClick={() => setShowAdvancedSync(!showAdvancedSync)}
                  className="text-xs font-bold text-neutral-400 hover:text-amber-600 uppercase tracking-widest transition-colors flex items-center gap-1.5 ml-2"
                >
                  {showAdvancedSync ? 'Hide Advanced' : 'Custom History'}
                  <Clock size={12} />
                </button>
              </div>

              <AnimatePresence>
                {showAdvancedSync && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="pt-2 border-t border-[var(--border)] mt-2 overflow-hidden"
                  >
                    <div className="bg-[var(--surface-high)] rounded-xl p-4 flex flex-col gap-3">
                      <label className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">
                        Sync from specific date (Historical)
                      </label>
                      <div className="flex items-center gap-3">
                        <input
                          type="date"
                          value={syncDate}
                          onChange={(e) => setSyncDate(e.target.value)}
                          className="px-4 py-2 border border-[var(--border)] rounded-xl text-sm focus:ring-2 focus:ring-amber-500/30 focus:border-amber-500 transition-all outline-none bg-[var(--surface-high)] text-[var(--text-primary)]"
                        />
                        <button
                          onClick={handleSync}
                          disabled={syncing || !syncDate}
                          className="px-4 py-2 bg-[var(--accent)] text-white rounded-xl text-xs font-bold hover:bg-[var(--accent-dark)] disabled:opacity-30 transition-all"
                        >
                          Trigger History Sync
                        </button>
                      </div>
                      <p className="text-[10px] text-amber-600 font-medium italic">
                        ⚠️ Rare scenario: This may take longer as it scans past web archives.
                      </p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>

          {/* Search & Download */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
            className="bg-[var(--surface-low)] rounded-2xl border border-[var(--border)] p-6 shadow-sm"
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-9 h-9 rounded-xl bg-blue-500/10 flex items-center justify-center">
                <Search size={18} className="text-blue-500" />
              </div>
              <div>
                <h3 className="font-bold text-[var(--text-primary)]">Search Case & Download Orders</h3>
                <p className="text-xs text-[var(--text-muted)]">Search NGT case → Solve CAPTCHA → Find & download order PDFs</p>
              </div>
            </div>

            <div className="flex flex-wrap items-end gap-4 mb-8">
              <div className="flex-1 min-w-[200px]">
                <label className="block text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest mb-2 px-1">Case Number / Year</label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={searchCaseNo}
                    onChange={(e) => {
                      const val = e.target.value;
                      setSearchCaseNo(val);
                      if (val.includes('/')) {
                        const parts = val.split('/');
                        if (parts[1] && parts[1].length === 4) {
                          setSearchCaseYear(parts[1]);
                        }
                      }
                    }}
                    placeholder="83/2025"
                    className="flex-1 px-4 py-3 bg-[var(--surface-high)] border border-[var(--border)] rounded-xl text-sm focus:ring-2 focus:ring-[var(--accent)]/30 focus:border-[var(--accent)] transition-all outline-none text-[var(--text-primary)]"
                  />
                  <input
                    type="text"
                    value={searchCaseYear}
                    onChange={(e) => setSearchCaseYear(e.target.value)}
                    placeholder="2025"
                    className="w-24 px-4 py-3 bg-[var(--surface-high)] border border-[var(--border)] rounded-xl text-sm focus:ring-2 focus:ring-[var(--accent)]/30 focus:border-[var(--accent)] transition-all outline-none text-[var(--text-primary)]"
                  />
                </div>
              </div>
              <div className="flex gap-4">
                <motion.button
                  whileTap={{ scale: 0.97 }}
                  onClick={handleSearch}
                  disabled={searching || !searchCaseNo.trim()}
                  className="px-6 py-3 bg-[var(--accent)] text-white rounded-xl font-bold text-sm shadow-xl shadow-[var(--accent)]/20 disabled:opacity-50 flex items-center gap-2 transition-all"
                >
                  {searching ? <Loader2 size={18} className="animate-spin" /> : <Search size={18} />}
                  {searching ? 'Searching...' : 'Search Case'}
                </motion.button>
                <motion.button
                  whileTap={{ scale: 0.97 }}
                  onClick={handleDownloadOrders}
                  disabled={downloading || !searchCaseNo.trim()}
                  className="px-6 py-3 bg-emerald-600 text-white rounded-xl font-bold text-sm shadow-xl shadow-emerald-600/20 disabled:opacity-50 flex items-center gap-2 transition-all"
                >
                  {downloading ? <Loader2 size={18} className="animate-spin" /> : <Download size={18} />}
                  {downloading ? 'Downloading...' : 'Download All'}
                </motion.button>
              </div>
            </div>

            {searchStatus && (
              <motion.div 
                initial={{ opacity: 0, y: -5 }}
                animate={{ opacity: 1, y: 0 }}
                className="mb-6 flex items-center gap-3 text-xs font-bold text-amber-600 bg-amber-500/5 border border-amber-500/20 px-4 py-3 rounded-xl"
              >
                <div className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
                <span className="uppercase tracking-widest">{searchStatus}</span>
              </motion.div>
            )}

            {/* Search Results */}
            <AnimatePresence>
              {searchResult && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="overflow-hidden"
                >
                  <div className={`rounded-lg p-4 ${searchResult.success ? 'bg-emerald-50 border border-emerald-200' : 'bg-red-50 border border-red-200'}`}>
                    {searchResult.success ? (
                      <>
                        <div className="flex items-center gap-2 mb-2">
                          <CheckCircle2 size={16} className="text-emerald-600" />
                          <span className="font-medium text-emerald-800 text-sm">
                            Diary Number: {searchResult.diary_number}
                          </span>
                        </div>
                        {searchResult.orders.length > 0 ? (
                          <div className="space-y-1.5 mt-3">
                            <p className="text-xs font-medium text-emerald-700">{searchResult.total_orders} Order(s) Found:</p>
                            {searchResult.orders.map((order, i) => (
                              <div key={i} className="flex items-center gap-2 text-xs text-emerald-700 bg-emerald-100/50 rounded-md px-3 py-1.5">
                                <FileText size={12} />
                                <span className="font-mono">{order.suggested_filename}</span>
                                <span className="text-emerald-500">[{order.order_date}]</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-emerald-600 mt-1">No downloadable orders found.</p>
                        )}
                      </>
                    ) : (
                      <div className="flex items-center gap-2">
                        <XCircle size={16} className="text-red-500" />
                        <span className="text-sm text-red-700">{searchResult.message || 'Search failed'}</span>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Download Results */}
            <AnimatePresence>
              {downloadResult && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="overflow-hidden mt-3"
                >
                  <div className={`rounded-lg p-4 ${downloadResult.success ? 'bg-blue-50 border border-blue-200' : 'bg-red-50 border border-red-200'}`}>
                    {downloadResult.success ? (
                      <>
                        <div className="flex items-center gap-2 mb-2">
                          <Download size={16} className="text-blue-600" />
                          <span className="font-medium text-blue-800 text-sm">{downloadResult.message}</span>
                        </div>
                        {downloadResult.downloaded.length > 0 && (
                          <div className="space-y-1 mt-2">
                            {downloadResult.downloaded.map((path, i) => (
                              <div key={i} className="text-xs text-blue-700 truncate font-mono bg-blue-100/50 rounded px-2 py-1">
                                {path.split('/').pop()}
                              </div>
                            ))}
                          </div>
                        )}
                        {(downloadResult.imported_to_notebook?.length || 0) > 0 && (
                          <div className="mt-2 flex items-center gap-1.5 text-xs text-emerald-600">
                            <Zap size={12} />
                            {downloadResult.imported_to_notebook.length} file(s) auto-imported to case notebook
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="flex items-center gap-2">
                        <XCircle size={16} className="text-red-500" />
                        <span className="text-sm text-red-700">{downloadResult.message}</span>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        </div>

        {/* Right Column: Activity Log */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
          className="bg-[var(--surface-low)] rounded-3xl border border-[var(--border)] p-6 shadow-xl h-fit lg:sticky lg:top-8"
        >
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Activity size={18} className="text-[var(--text-muted)]" />
              <h3 className="font-bold text-[var(--text-primary)] uppercase tracking-widest text-xs">Activity Log</h3>
            </div>
            <span className="text-[10px] font-bold text-[var(--text-muted)]">{activityLog.length} Items</span>
          </div>

          {activityLog.length === 0 ? (
            <div className="text-center py-8">
              <Clock size={24} className="mx-auto text-neutral-300 mb-2" />
              <p className="text-sm text-neutral-400">No activity yet</p>
              <p className="text-xs text-neutral-300 mt-1">Start a sync or search to see activity</p>
            </div>
          ) : (
            <div className="space-y-2 max-h-[500px] overflow-y-auto scrollbar-thin">
              {activityLog.map((item) => (
                <motion.div
                  key={item.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className={`rounded-lg px-3 py-2.5 text-xs border ${
                    item.type === 'error'
                      ? 'bg-red-50 border-red-100 text-red-700'
                      : item.type === 'sync'
                      ? 'bg-amber-50 border-amber-100 text-amber-700'
                      : item.type === 'download'
                      ? 'bg-blue-50 border-blue-100 text-blue-700'
                      : 'bg-emerald-50 border-emerald-100 text-emerald-700'
                  }`}
                >
                  <div className="flex items-start gap-2">
                    {item.type === 'error' ? (
                      <AlertTriangle size={12} className="mt-0.5 flex-shrink-0" />
                    ) : item.type === 'sync' ? (
                      <RefreshCw size={12} className="mt-0.5 flex-shrink-0" />
                    ) : item.type === 'download' ? (
                      <Download size={12} className="mt-0.5 flex-shrink-0" />
                    ) : (
                      <Search size={12} className="mt-0.5 flex-shrink-0" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{item.message}</p>
                      {item.details && (
                        <p className="opacity-70 mt-0.5 truncate">{item.details}</p>
                      )}
                    </div>
                    <span className="text-[10px] opacity-50 flex-shrink-0">{item.timestamp}</span>
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </motion.div>
      </div>
      {/* Manual CAPTCHA Modal */}
      <AnimatePresence>
        {captchaModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setCaptchaModalOpen(false)}
              className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            />
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="relative bg-[var(--surface-high)] w-full max-w-md rounded-2xl border border-[var(--border)] shadow-2xl p-8 overflow-hidden"
            >
              <div className="flex items-center gap-3 mb-6">
                <div className="w-10 h-10 bg-amber-500/10 rounded-xl flex items-center justify-center text-amber-600">
                  <AlertTriangle size={24} />
                </div>
                <div>
                  <h3 className="text-xl font-bold text-[var(--text-primary)]">Human Verification</h3>
                  <p className="text-xs text-[var(--text-muted)] mt-1 font-medium italic">Court systems require a final human verification.</p>
                </div>
              </div>

              <div className="space-y-6">
                <div className="bg-white rounded-xl p-6 border border-[var(--border)] flex items-center justify-center shadow-inner">
                  <img src={`data:image/png;base64,${captchaImage}`} alt="Court CAPTCHA" className="h-16 object-contain" />
                </div>
                
                <div className="space-y-2">
                  <label className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest px-1">Case Verification Code</label>
                  <input
                    type="text"
                    value={manualCaptchaText}
                    onChange={(e) => setManualCaptchaText(e.target.value.toUpperCase())}
                    placeholder="Enter characters exactly as shown"
                    className="w-full px-4 py-4 bg-[var(--surface-low)] border-2 border-[var(--border)] rounded-xl text-lg font-bold tracking-[0.2em] text-center text-[var(--text-primary)] focus:border-amber-500 outline-none transition-all"
                  />
                </div>

                <div className="flex gap-3 pt-2">
                   <button 
                    onClick={() => setCaptchaModalOpen(false)}
                    className="flex-1 py-3.5 px-4 rounded-xl font-bold text-sm text-[var(--text-muted)] hover:bg-[var(--surface-low)] transition-colors"
                   >
                     Cancel
                   </button>
                   <button 
                    onClick={handleManualCaptchaSubmit}
                    disabled={isSubmittingManual || !manualCaptchaText.trim()}
                    className="flex-1 py-3.5 px-4 rounded-xl font-bold text-sm bg-amber-500 text-white hover:bg-amber-600 shadow-lg shadow-amber-500/30 disabled:opacity-50 flex items-center justify-center gap-2 transition-all"
                   >
                     {isSubmittingManual ? <Loader2 size={18} className="animate-spin" /> : <CheckCircle2 size={18} />}
                     Verify & Search
                   </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default ScraperPage;
