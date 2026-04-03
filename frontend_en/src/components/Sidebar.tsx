import React from 'react';
import { motion } from 'framer-motion';
import { 
  LayoutGrid, 
  Globe, 
  Calendar, 
  FileText, 
  Scale, 
  Settings,
  LogOut,
  ChevronRight,
  ChevronLeft,
  Search,
  BookOpen
} from 'lucide-react';
import { useAuthStore } from '../stores/authStore';

interface SidebarProps {
  currentView: string;
  onNavigate: (view: string) => void;
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ currentView, onNavigate, collapsed, setCollapsed }) => {
  const { signOut } = useAuthStore();

  const navItems = [
    { id: 'dashboard', label: 'Portfolio', icon: LayoutGrid, description: 'Case Management' },
    { id: 'scraper', label: 'Court Sync', icon: Globe, description: 'NGT Data Engine' },
    { id: 'calendar', label: 'Calendar', icon: Calendar, description: 'Hearing Schedule' },
    { id: 'reports', label: 'Analytics', icon: FileText, description: 'AI Intelligence' },
  ];

  return (
    <motion.aside
      initial={false}
      animate={{ width: collapsed ? 80 : 280 }}
      className="h-screen sticky top-0 bg-[var(--surface-high)] border-r border-[var(--border)] flex flex-col z-40 transition-colors duration-500"
    >
      {/* Branding */}
      <div className="p-6 flex items-center gap-3">
        <div className="w-10 h-10 bg-[var(--accent)] rounded-xl flex items-center justify-center text-white shadow-lg shrink-0">
          <Scale size={24} />
        </div>
        {!collapsed && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="overflow-hidden whitespace-nowrap"
          >
            <h1 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">LawNidhi</h1>
            <p className="text-[10px] font-bold text-[var(--accent)] uppercase tracking-[0.2em]">Enterprise</p>
          </motion.div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-4 py-6 space-y-2">
        {navItems.map((item) => (
          <motion.button
            key={item.id}
            whileHover={{ x: 4 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => onNavigate(item.id)}
            className={`w-full flex items-center gap-3 p-3 rounded-xl transition-all relative group ${
              currentView === item.id 
                ? 'bg-[var(--accent-soft)] text-[var(--accent)]' 
                : 'text-[var(--text-secondary)] hover:bg-[var(--surface-low)] hover:text-[var(--text-primary)]'
            }`}
          >
            <item.icon size={22} className="shrink-0" />
            {!collapsed && (
              <div className="text-left overflow-hidden">
                <p className="text-sm font-bold truncate">{item.label}</p>
                <p className={`text-[10px] truncate ${currentView === item.id ? 'text-[var(--accent)]/70' : 'text-[var(--text-muted)]'}`}>
                  {item.description}
                </p>
              </div>
            )}
            {!collapsed && currentView === item.id && (
              <motion.div 
                layoutId="activeIndicator"
                className="absolute right-2 w-1.5 h-1.5 rounded-full bg-[var(--accent)]" 
              />
            )}
            {collapsed && (
               <div className="absolute left-full ml-4 px-2 py-1 bg-[var(--surface-high)] border border-[var(--border)] rounded text-xs text-[var(--text-primary)] opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50 shadow-xl">
                 {item.label}
               </div>
            )}
          </motion.button>
        ))}
      </nav>

      {/* Footer Actions */}
      <div className="p-4 border-t border-[var(--border)] space-y-2">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center gap-3 p-3 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors rounded-xl"
        >
          {collapsed ? <ChevronRight size={20} /> : (
            <>
              <ChevronLeft size={20} />
              <span className="text-xs font-bold uppercase tracking-widest">Collapse</span>
            </>
          )}
        </button>
        
        <button
          onClick={() => void signOut()}
          className="w-full flex items-center gap-3 p-3 text-[var(--text-secondary)] hover:text-rose-500 transition-colors rounded-xl group relative"
        >
          <LogOut size={20} />
          {!collapsed && <span className="text-xs font-bold uppercase tracking-widest">Sign Out</span>}
          {collapsed && (
            <div className="absolute left-full ml-4 px-2 py-1 bg-[var(--surface-high)] border border-[var(--border)] rounded text-xs text-rose-500 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50 shadow-xl">
              Sign Out
            </div>
          )}
        </button>
      </div>
    </motion.aside>
  );
};

export default Sidebar;
