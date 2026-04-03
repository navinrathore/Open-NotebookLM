import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Dashboard from './pages/Dashboard';
import NotebookView from './pages/NotebookView';
import ScraperPage from './pages/ScraperPage';
import CaseDetailPage from './pages/CaseDetailPage';
import CalendarPage from './pages/CalendarPage';
import ReportsPage from './pages/ReportsPage';
import AuthPage from './pages/AuthPage';
import { useAuthStore } from './stores/authStore';
import { initSupabase, refreshSession } from './lib/supabase';
import { Loader2 } from 'lucide-react';
import { Case } from './types/case';
import Sidebar from './components/Sidebar';

const pageVariants = {
  initial: (direction: number) => ({
    x: direction > 0 ? 20 : -20,
    opacity: 0,
  }),
  animate: {
    x: 0,
    opacity: 1,
    transition: { type: 'spring', stiffness: 300, damping: 30 },
  },
  exit: (direction: number) => ({
    x: direction > 0 ? -20 : 20,
    opacity: 0,
    transition: { duration: 0.2 },
  }),
};

function App() {
  const [currentView, setCurrentView] = useState<'dashboard' | 'notebook' | 'scraper' | 'case-detail' | 'calendar' | 'reports'>('dashboard');
  const [selectedNotebook, setSelectedNotebook] = useState<any>(null);
  const [selectedCase, setSelectedCase] = useState<Case | null>(null);
  const [dashboardRefresh, setDashboardRefresh] = useState(0);
  const [direction, setDirection] = useState(0);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [supabaseConfigured, setSupabaseConfigured] = useState<boolean | null>(null);
  const { user, loading, setUser } = useAuthStore();

  // Initialize Supabase from backend config
  useEffect(() => {
    initSupabase().then(setSupabaseConfigured);
  }, []);

  // Initialize auth session
  useEffect(() => {
    if (supabaseConfigured === null) return;
    if (!supabaseConfigured) {
      setUser(null);
      return;
    }

    refreshSession().then(setUser);
  }, [setUser, supabaseConfigured]);

  useEffect(() => {
    if (!user) {
      setCurrentView('dashboard');
      setSelectedNotebook(null);
    }
  }, [user]);

  if (loading || supabaseConfigured === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--surface)]">
        <Loader2 size={28} className="animate-spin text-[var(--text-muted)]" />
      </div>
    );
  }

  // If Supabase is configured but user is not logged in, show auth page
  if (supabaseConfigured && !user) {
    return <AuthPage />;
  }

  // If Supabase is not configured, allow trial mode (no auth required)

  const handleOpenNotebook = (notebook: any) => {
    setSelectedNotebook(notebook);
    setDirection(1);
    setCurrentView('notebook');
  };

  const handleBackToDashboard = () => {
    setDirection(-1);
    setCurrentView('dashboard');
    setSelectedNotebook(null);
    setSelectedCase(null);
    setDashboardRefresh((n) => n + 1);
  };

  const handleOpenScraper = () => {
    setDirection(1);
    setCurrentView('scraper');
  };

  const handleOpenCase = (c: Case) => {
    setSelectedCase(c);
    setDirection(1);
    setCurrentView('case-detail');
  };

  const handleOpenCalendar = () => {
    setDirection(1);
    setCurrentView('calendar');
  };

  const handleNavigate = (view: string) => {
    setDirection(view === 'dashboard' ? -1 : 1);
    setCurrentView(view as any);
  };

  return (
    <div className="flex min-h-screen bg-[var(--surface)] transition-colors duration-500 overflow-hidden">
      {/* Persistent Navigation for LawNidhi Suite */}
      {user && (
        <Sidebar
          currentView={currentView}
          onNavigate={handleNavigate}
          collapsed={sidebarCollapsed}
          setCollapsed={setSidebarCollapsed}
        />
      )}

      <main className="flex-1 relative h-screen overflow-y-auto">
        <AnimatePresence mode="wait" custom={direction}>
        {currentView === 'dashboard' ? (
          <motion.div
            key="dashboard"
            custom={direction}
            variants={pageVariants}
            initial="initial"
            animate="animate"
            exit="exit"
          >
            <Dashboard 
              onOpenNotebook={handleOpenNotebook} 
              onOpenCase={handleOpenCase}
              onOpenScraper={handleOpenScraper}
              onOpenCalendar={handleOpenCalendar}
              onOpenReports={() => handleNavigate('reports')}
              refreshTrigger={dashboardRefresh} 
              supabaseConfigured={supabaseConfigured} 
            />
          </motion.div>
        ) : currentView === 'scraper' ? (
          <motion.div
            key="scraper"
            custom={direction}
            variants={pageVariants}
            initial="initial"
            animate="animate"
            exit="exit"
          >
            <ScraperPage onBack={handleBackToDashboard} />
          </motion.div>
        ) : currentView === 'case-detail' ? (
          <motion.div
            key="case-detail"
            custom={direction}
            variants={pageVariants}
            initial="initial"
            animate="animate"
            exit="exit"
          >
            <CaseDetailPage 
              caseItem={selectedCase!} 
              onBack={handleBackToDashboard} 
            />
          </motion.div>
        ) : currentView === 'calendar' ? (
          <motion.div
            key="calendar"
            custom={direction}
            variants={pageVariants}
            initial="initial"
            animate="animate"
            exit="exit"
          >
            <CalendarPage onBack={handleBackToDashboard} />
          </motion.div>
        ) : currentView === 'reports' ? (
          <motion.div
            key="reports"
            custom={direction}
            variants={pageVariants}
            initial="initial"
            animate="animate"
            exit="exit"
          >
            <ReportsPage onBack={handleBackToDashboard} />
          </motion.div>
        ) : (
          <motion.div
            key="notebook"
            custom={direction}
            variants={pageVariants}
            initial="initial"
            animate="animate"
            exit="exit"
          >
            <NotebookView
              notebook={selectedNotebook}
              onBack={handleBackToDashboard}
            />
          </motion.div>
        )}
      </AnimatePresence>
      </main>
    </div>
  );
}

export default App;

