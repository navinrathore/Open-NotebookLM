import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  ChevronLeft, FileText, Download, PieChart, BarChart3,
  Search, Calendar, User, Printer, Copy, CheckCircle2,
  AlertCircle, ArrowRight, TrendingUp, Briefcase, Scale, Loader2, Zap
} from 'lucide-react';
import { apiFetch } from '../config/api';
import ThemeToggle from '../components/ThemeToggle';

// ----------- Types -----------

interface Stats {
  total_cases: number;
  status_counts: Record<string, number>;
  total_schedules: number;
  db_stats: Record<string, number>;
}

// ----------- Component -----------

const ReportsPage = ({ onBack }: { onBack: () => void }) => {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loadingStats, setLoadingStats] = useState(true);
  
  // Report Form
  const [counsels, setCounsels] = useState<string[]>([]);
  const [selectedCounsel, setSelectedCounsel] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [generating, setGenerating] = useState(false);
  const [reportText, setReportText] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetchStats();
    fetchCounsels();
  }, []);

  const fetchStats = async () => {
    setLoadingStats(true);
    try {
      const res = await apiFetch('/api/v1/reports/case-stats');
      const data = await res.json();
      if (data.success) {
        setStats(data);
      }
    } catch (err) {
      console.error('Failed to fetch stats:', err);
    } finally {
      setLoadingStats(false);
    }
  };

  const fetchCounsels = async () => {
    try {
      const res = await apiFetch('/api/v1/reports/counsels');
      const data = await res.json();
      if (data.success) {
        setCounsels(data.counsels);
        if (data.counsels.length > 0) setSelectedCounsel(data.counsels[0]);
      }
    } catch (err) {
      console.error('Failed to fetch counsels:', err);
    }
  };

  const handleGenerateReport = async () => {
    if (!selectedCounsel) return;
    setGenerating(true);
    setReportText(null);
    try {
      const res = await apiFetch('/api/v1/reports/appearance-log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          counsel: selectedCounsel,
          start_date: startDate || null,
          end_date: endDate || null
        })
      });
      const data = await res.json();
      if (data.success) {
        setReportText(data.report_text);
      }
    } catch (err) {
      console.error('Failed to generate report:', err);
    } finally {
      setGenerating(false);
    }
  };

  const handleCopy = () => {
    if (reportText) {
      navigator.clipboard.writeText(reportText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-8 transition-colors duration-500 min-h-screen">
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
            <div>
              <h1 className="text-3xl font-bold text-[var(--text-primary)] tracking-tight font-display">Intelligence Reports</h1>
              <p className="text-[var(--text-secondary)] font-medium mt-1">Analytics, appearance logs, and insights</p>
            </div>
          </div>
          <ThemeToggle />
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: 'Total Portfolio Cases', value: stats?.total_cases || 0, icon: Briefcase, color: 'text-blue-600', bg: 'bg-blue-50' },
            { label: 'Listed Hearings', value: stats?.total_schedules || 0, icon: Calendar, color: 'text-amber-600', bg: 'bg-amber-50' },
            { label: 'Identified Counsels', value: stats?.db_stats?.counsels || 0, icon: User, color: 'text-purple-600', bg: 'bg-purple-50' },
            { label: 'Active Efficiency', value: '94%', icon: TrendingUp, color: 'text-emerald-600', bg: 'bg-emerald-50' }
          ].map((item, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="bg-[var(--surface-low)] p-5 rounded-2xl border border-[var(--border)] shadow-sm backdrop-blur-sm"
            >
              <div className="flex items-center gap-3 mb-3">
                <div className={`w-10 h-10 rounded-xl ${item.bg} flex items-center justify-center`}>
                  <item.icon size={20} className={item.color} />
                </div>
                <span className="text-xs font-bold text-neutral-400 uppercase tracking-widest">{item.label}</span>
              </div>
              <p className="text-2xl font-bold text-[var(--text-primary)] leading-none">{loadingStats ? '...' : item.value}</p>
            </motion.div>
          ))}
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left: Report Generator Form */}
        <div className="lg:col-span-12 xl:col-span-4 space-y-6">
          <div className="bg-[var(--surface-low)] rounded-3xl border border-[var(--border)] shadow-xl p-8">
            <h3 className="text-xl font-bold text-[var(--text-primary)] mb-6 flex items-center gap-3">
              <Scale size={20} className="text-[var(--accent)]" /> Appearance Log
            </h3>
            
            <div className="space-y-5">
              <div>
                <label className="block text-xs font-bold text-neutral-400 uppercase tracking-widest mb-2 px-1">Select Counsel</label>
                <select 
                  value={selectedCounsel}
                  onChange={(e) => setSelectedCounsel(e.target.value)}
                  className="w-full px-4 py-3 bg-[var(--surface-high)] border border-[var(--border)] rounded-xl text-sm focus:ring-2 focus:ring-[var(--accent)]/30 focus:border-[var(--accent)] transition-all outline-none appearance-none text-[var(--text-primary)]"
                >
                  <option value="">Choose a counsel...</option>
                  {counsels.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <input 
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-full px-4 py-4 bg-[var(--surface-high)] border border-[var(--border)] rounded-xl text-sm focus:ring-2 focus:ring-[var(--accent)]/30 focus:border-[var(--accent)] transition-all outline-none text-[var(--text-primary)]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest mb-2 px-1">End Date</label>
                  <input 
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="w-full px-4 py-4 bg-[var(--surface-high)] border border-[var(--border)] rounded-xl text-sm focus:ring-2 focus:ring-[var(--accent)]/30 focus:border-[var(--accent)] transition-all outline-none text-[var(--text-primary)]"
                  />
                </div>
              </div>

              <motion.button
                whileTap={{ scale: 0.98 }}
                onClick={handleGenerateReport}
                disabled={generating || !selectedCounsel}
                className="w-full py-4 bg-[var(--text-primary)] hover:opacity-90 text-[var(--surface)] rounded-xl font-bold shadow-xl shadow-neutral-500/20 disabled:opacity-50 transition-all flex items-center justify-center gap-3 mt-6"
              >
                {generating ? <Loader2 size={18} className="animate-spin" /> : <Zap size={18} className="text-amber-400" />}
                {generating ? 'Processing Data...' : 'Generate Appearance Record'}
              </motion.button>
            </div>
          </div>

          <div className="bg-blue-600 rounded-3xl p-8 text-white relative overflow-hidden shadow-xl">
            <div className="relative z-10">
              <h4 className="font-bold text-lg mb-2">Automated Billing</h4>
              <p className="text-sm text-blue-100 mb-6 leading-relaxed">
                LawNidhi cross-references cause lists with your portfolio to verify exactly which matters were attended.
              </p>
              <button className="flex items-center gap-2 text-xs font-bold bg-white/20 hover:bg-white/30 px-4 py-2 rounded-lg transition-colors border border-white/20">
                Setup Invoicing Rules <ArrowRight size={14} />
              </button>
            </div>
            <Printer className="absolute -bottom-4 -right-4 w-32 h-32 text-white/10" />
          </div>
        </div>

        {/* Right: Report Viewer */}
        <div className="lg:col-span-12 xl:col-span-8">
          <AnimatePresence mode="wait">
            {!reportText ? (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="bg-[var(--surface-low)] rounded-3xl border-2 border-dashed border-[var(--border)] p-20 flex flex-col items-center text-center justify-center h-full min-h-[500px]"
              >
                <div className="w-20 h-20 bg-[var(--surface-high)] rounded-2xl flex items-center justify-center mb-6 border border-[var(--border)] text-[var(--text-muted)]">
                  <FileText className="opacity-40" size={40} />
                </div>
                <h3 className="text-xl font-bold text-[var(--text-primary)] mb-2">No Report Active</h3>
                <p className="text-[var(--text-secondary)] max-w-sm">
                  Configure your filters on the left to generate a detailed appearance log for your selection.
                </p>
              </motion.div>
            ) : (
              <motion.div
                key="report"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-[var(--surface-low)] rounded-3xl border border-[var(--border)] shadow-2xl flex flex-col h-full min-h-[600px] overflow-hidden"
              >
                <div className="border-b border-[var(--border)] p-6 flex flex-wrap items-center justify-between gap-4 bg-[var(--surface-high)]/30 backdrop-blur-sm">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
                      <CheckCircle2 size={16} />
                    </div>
                    <span className="font-bold text-[var(--text-primary)]">Verified Result for "{selectedCounsel}"</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button 
                      onClick={handleCopy}
                      className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-[var(--text-secondary)] hover:bg-[var(--surface-high)] font-bold text-xs transition-all border border-[var(--border)]"
                    >
                      {copied ? <CheckCircle2 size={14} className="text-emerald-500" /> : <Copy size={14} />}
                      {copied ? 'Copied!' : 'Copy Logic'}
                    </button>
                    <button className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[var(--accent)] text-white font-bold text-xs hover:bg-[var(--accent-dark)] transition-all shadow-lg shadow-[var(--accent)]/20">
                      <Download size={14} /> Export Text
                    </button>
                  </div>
                </div>

                <div className="flex-1 p-8 overflow-y-auto bg-[var(--surface)]/50">
                  <div className="bg-[var(--surface-low)] rounded-2xl border border-[var(--border)] shadow-sm p-10 font-mono text-sm text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap selection:bg-[var(--accent-soft)]">
                    {reportText}
                  </div>
                </div>

                <div className="p-6 border-t border-[var(--border)] bg-[var(--surface-high)]/30 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="flex items-center gap-2 text-xs font-medium text-[var(--text-secondary)]">
                    <AlertCircle size={14} className="text-blue-500" />
                    <span>Data sourced directly from parsed NGT daily order lists.</span>
                  </div>
                  <span className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">
                    Generated: {new Date().toLocaleDateString()}
                  </span>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
};

export default ReportsPage;
