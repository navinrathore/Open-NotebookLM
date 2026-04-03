import React, { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  ChevronLeft, ChevronRight, Calendar as CalendarIcon, 
  MapPin, User, Scale, Clock, AlertCircle, 
  Search, Filter, ExternalLink, ArrowRight, Zap, Menu
} from 'lucide-react';
import { apiFetch } from '../config/api';
import ThemeToggle from '../components/ThemeToggle';

// ----------- Types -----------

interface Hearing {
  case_number: string;
  case_year: string;
  diary_number?: string;
  schedule_date: string;
  court_no: string;
  judge_name: string;
}

// ----------- Helper Functions -----------

const getDaysInMonth = (year: number, month: number) => {
  return new Date(year, month + 1, 0).getDate();
};

const getFirstDayOfMonth = (year: number, month: number) => {
  return new Date(year, month, 1).getDay();
};

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];

// ----------- Component -----------

const CalendarPage = ({ onBack }: { onBack: () => void }) => {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [hearings, setHearings] = useState<Hearing[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  // Fetch hearings on load
  useEffect(() => {
    fetchHearings();
  }, []);

  const fetchHearings = async () => {
    setLoading(true);
    try {
      const res = await apiFetch('/api/v1/calendar/hearings');
      const data = await res.json();
      if (data.success) {
        setHearings(data.hearings);
      }
    } catch (err) {
      console.error('Failed to fetch hearings:', err);
    } finally {
      setLoading(false);
    }
  };

  // Group hearings by date for easy lookup
  const hearingsByDate = useMemo(() => {
    const map: Record<string, Hearing[]> = {};
    hearings.forEach(h => {
      if (!map[h.schedule_date]) map[h.schedule_date] = [];
      map[h.schedule_date].push(h);
    });
    return map;
  }, [hearings]);

  // Calendar Logic
  const daysInMonth = getDaysInMonth(year, month);
  const firstDay = getFirstDayOfMonth(year, month);
  const days = [];

  // Padding for start of month
  for (let i = 0; i < firstDay; i++) {
    days.push(null);
  }
  // Month days
  for (let i = 1; i <= daysInMonth; i++) {
    days.push(i);
  }

  const navigateMonth = (direction: number) => {
    setCurrentDate(new Date(year, month + direction, 1));
  };

  const formatDateString = (day: number) => {
    const d = day.toString().padStart(2, '0');
    const m = (month + 1).toString().padStart(2, '0');
    return `${year}-${m}-${d}`;
  };

  const selectedHearings = selectedDate ? hearingsByDate[selectedDate] || [] : [];

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-8 transition-colors duration-500 min-h-screen">
      {/* Header */}
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-10">
        <div className="flex items-center gap-4">
          <motion.button
            whileTap={{ scale: 0.95 }}
            onClick={onBack}
            className="p-2.5 rounded-xl hover:bg-[var(--surface-high)] transition-colors text-[var(--text-secondary)] border border-[var(--border)] shadow-sm bg-[var(--surface-low)]"
          >
            <ChevronLeft size={20} />
          </motion.button>
          <div>
            <h1 className="text-3xl font-bold text-[var(--text-primary)] tracking-tight font-display">Hearing Calendar</h1>
            <p className="text-[var(--text-secondary)] font-medium mt-1">Track your court appearances across all benches</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <ThemeToggle />
          <div className="flex items-center bg-[var(--surface-low)] p-1 rounded-xl border border-[var(--border)] shadow-sm backdrop-blur-md">
            <button 
              onClick={() => navigateMonth(-1)}
              className="p-2 hover:bg-[var(--surface-high)] rounded-lg text-[var(--text-secondary)] transition-colors"
            >
              <ChevronLeft size={20} />
            </button>
            <div className="px-6 py-1.5 min-w-[140px] text-center">
              <span className="font-bold text-[var(--text-primary)]">{MONTHS[month]}</span>
              <span className="text-[var(--text-muted)] font-medium ml-1.5">{year}</span>
            </div>
            <button 
              onClick={() => navigateMonth(1)}
              className="p-2 hover:bg-[var(--surface-high)] rounded-lg text-[var(--text-secondary)] transition-colors"
            >
              <ChevronRight size={20} />
            </button>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Main Calendar Grid */}
        <div className="lg:col-span-8 bg-[var(--surface-low)] rounded-3xl border border-[var(--border)] shadow-xl overflow-hidden relative">
          <div className="grid grid-cols-7 border-b border-[var(--border)] bg-[var(--surface-high)]/50 backdrop-blur-sm">
            {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(d => (
              <div key={d} className="py-4 text-center text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">{d}</div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {days.map((day, idx) => {
              if (day === null) return <div key={`empty-${idx}`} className="h-24 sm:h-32 border-b border-r border-neutral-50 bg-neutral-50/30" />;
              
              const dateStr = formatDateString(day);
              const dateHearings = hearingsByDate[dateStr] || [];
              const isSelected = selectedDate === dateStr;
              const isToday = new Date().toDateString() === new Date(year, month, day).toDateString();

              return (
                <motion.div
                  key={dateStr}
                  whileHover={{ backgroundColor: 'var(--surface-high)' }}
                  onClick={() => setSelectedDate(dateStr)}
                  className={`h-24 sm:h-32 p-2 border-b border-r border-[var(--border)] cursor-pointer transition-all relative ${isSelected ? 'bg-[var(--accent-soft)] shadow-inner' : ''}`}
                >
                  <div className="flex items-center justify-between">
                    <span className={`text-sm font-bold w-8 h-8 flex items-center justify-center rounded-xl transition-all ${
                      isToday ? 'bg-[var(--text-primary)] text-[var(--surface)] shadow-lg scale-110' : 
                      isSelected ? 'text-[var(--accent)] bg-[var(--accent-soft)] ring-2 ring-[var(--accent)]' : 'text-[var(--text-secondary)]'
                    }`}>
                      {day}
                    </span>
                    {dateHearings.length > 0 && (
                      <span className="text-[10px] bg-[var(--surface-high)] text-[var(--text-secondary)] px-1.5 py-0.5 rounded-lg font-bold border border-[var(--border)] shadow-sm">
                        {dateHearings.length}
                      </span>
                    )}
                  </div>

                  <div className="mt-2 space-y-1 overflow-hidden h-[calc(100%-2rem)]">
                    {dateHearings.slice(0, 2).map((h, i) => (
                      <div 
                        key={i} 
                        className={`text-[9px] sm:text-[10px] px-1.5 py-1 rounded-md border truncate font-medium ${
                          h.court_no === '1' ? 'bg-blue-50 border-blue-100 text-blue-700' :
                          h.court_no === '2' ? 'bg-purple-50 border-purple-100 text-purple-700' :
                          'bg-neutral-50 border-neutral-100 text-neutral-600'
                        }`}
                      >
                        {h.case_number}/{h.case_year}
                      </div>
                    ))}
                    {dateHearings.length > 2 && (
                      <div className="text-[9px] text-neutral-400 font-bold pl-1">
                        + {dateHearings.length - 2} more
                      </div>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>

        {/* Sidebar: Selected Date Details */}
        <div className="lg:col-span-4 space-y-6">
          <AnimatePresence mode="wait">
            {!selectedDate ? (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="bg-neutral-50 border-2 border-dashed border-neutral-200 rounded-3xl p-8 text-center"
              >
                <div className="w-16 h-16 bg-white rounded-2xl flex items-center justify-center shadow-sm mx-auto mb-4 border border-neutral-100">
                  <Clock className="text-neutral-300" size={32} />
                </div>
                <h3 className="font-bold text-neutral-800 mb-2">No Date Selected</h3>
                <p className="text-sm text-neutral-500">Pick a calendar date to view the listed headings and case details.</p>
              </motion.div>
            ) : (
              <motion.div
                key={selectedDate}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="space-y-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-bold text-neutral-900 text-lg">
                    {new Date(selectedDate).toLocaleDateString('en-US', { day: 'numeric', month: 'long', year: 'numeric' })}
                  </h3>
                  <span className="text-xs font-bold text-neutral-400 uppercase tracking-widest">
                    {selectedHearings.length} Hearings
                  </span>
                </div>

                {selectedHearings.length === 0 ? (
                  <div className="bg-white rounded-2xl p-6 border border-neutral-200 text-center text-neutral-400 text-sm">
                    No hearings scheduled for this date.
                  </div>
                ) : (
                  <div className="space-y-4">
                    {selectedHearings.map((h, i) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.05 }}
                        className="bg-white rounded-2xl border border-neutral-200 p-5 shadow-sm hover:shadow-md transition-all group"
                      >
                        <div className="flex items-start justify-between mb-4">
                          <div className="flex items-center gap-3">
                            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                              h.court_no === '1' ? 'bg-blue-50 text-blue-600' : 'bg-purple-50 text-purple-600'
                            }`}>
                              <Scale size={20} />
                            </div>
                            <div>
                              <h4 className="font-bold text-neutral-900">{h.case_number}/{h.case_year}</h4>
                              <span className="text-[10px] font-bold text-neutral-400 uppercase tracking-widest">
                                Court No. {h.court_no}
                              </span>
                            </div>
                          </div>
                          <button className="p-2 text-neutral-300 hover:text-accent-500 transition-colors opacity-0 group-hover:opacity-100">
                            <ExternalLink size={18} />
                          </button>
                        </div>
                        
                        <div className="space-y-3">
                          <div className="flex items-start gap-2.5">
                            <User size={14} className="text-neutral-400 mt-0.5" />
                            <div className="text-xs">
                              <p className="font-bold text-neutral-800">{h.judge_name || 'N/A'}</p>
                              <p className="text-neutral-400">Presiding Judge</p>
                            </div>
                          </div>
                        </div>

                        <div className="mt-4 pt-4 border-t border-neutral-50 flex items-center justify-between">
                          <span className="inline-flex items-center gap-1 text-[10px] font-bold bg-neutral-100 text-neutral-600 px-2 py-1 rounded-md uppercase tracking-tighter">
                            <Clock size={10} /> List Type: Final
                          </span>
                          <button className="text-[10px] font-bold text-neutral-400 hover:text-neutral-900 flex items-center gap-1 transition-colors group/btn">
                            View Status <ArrowRight size={10} className="group-hover/btn:translate-x-1 transition-transform" />
                          </button>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Tips Section */}
          <div className="bg-gradient-to-br from-neutral-800 to-neutral-950 rounded-3xl p-6 text-white shadow-xl relative overflow-hidden">
            <Zap className="absolute -top-2 -right-2 text-white/10 w-24 h-24" />
            <h4 className="font-semibold mb-2 flex items-center gap-2">
              <AlertCircle size={16} className="text-amber-400" /> Pro Tip
            </h4>
            <p className="text-xs text-neutral-300 leading-relaxed mb-4">
              Daily schedules are synced at 10 AM. If you don't see a hearing, please trigger a 
              <strong> Scraper Sync</strong> from the dashboard.
            </p>
            <button className="w-full py-2 bg-white/10 hover:bg-white/20 rounded-xl text-xs font-bold transition-all border border-white/10">
              Refresh Schedules
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CalendarPage;
