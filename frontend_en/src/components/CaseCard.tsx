import React from 'react';
import { motion } from 'framer-motion';
import { Scale, Calendar, FileText, ChevronRight, User, Briefcase } from 'lucide-react';
import { Case } from '../types/case';

interface CaseCardProps {
  caseItem: Case;
  onClick: (caseItem: Case) => void;
}

const StatusBadge = ({ status }: { status: string }) => {
  const getStatusStyles = (s: string) => {
    switch (s.toUpperCase()) {
      case 'NEW':
        return 'bg-blue-50 text-blue-600 border-blue-100 dark:bg-blue-900/20 dark:text-blue-400 dark:border-blue-800/30';
      case 'ACTIVE':
        return 'bg-emerald-50 text-emerald-600 border-emerald-100 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800/30';
      case 'CLOSED':
      case 'DISPOSED':
        return 'bg-neutral-100 text-neutral-500 border-neutral-200 dark:bg-neutral-800 dark:text-neutral-400 dark:border-neutral-700';
      case 'PENDING':
        return 'bg-amber-50 text-amber-600 border-amber-100 dark:bg-amber-900/20 dark:text-amber-400 dark:border-amber-800/30';
      default:
        return 'bg-neutral-50 text-neutral-400 border-neutral-100 dark:bg-neutral-900/10 dark:text-neutral-500 dark:border-neutral-800';
    }
  };

  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border tracking-wider uppercase ${getStatusStyles(status)}`}>
      {status}
    </span>
  );
};

const CaseCard: React.FC<CaseCardProps> = ({ caseItem, onClick }) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -4, shadow: 'var(--shadow)' }}
      whileTap={{ scale: 0.98 }}
      className="bg-[var(--surface-low)] dark:bg-neutral-900 rounded-2xl border border-[var(--border)] p-6 shadow-sm hover:border-[var(--accent)] transition-all cursor-pointer group flex flex-col h-full overflow-hidden relative"
      onClick={() => onClick(caseItem)}
    >
      <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-br from-[var(--accent)] to-transparent opacity-0 group-hover:opacity-[0.03] transition-opacity duration-500" />
      
      <div className="flex justify-between items-start mb-6">
        <div className="w-10 h-10 rounded-xl bg-[var(--surface-high)] dark:bg-neutral-800 flex items-center justify-center text-[var(--text-secondary)] group-hover:bg-[var(--accent-soft)] group-hover:text-[var(--accent)] transition-all">
          <Scale size={20} />
        </div>
        <StatusBadge status={caseItem.status} />
      </div>

      <div className="flex-1">
        <h3 className="text-lg font-bold text-[var(--text-primary)] font-display mb-1 group-hover:text-[var(--accent)] transition-colors leading-tight">
          {caseItem.case_number}/{caseItem.case_year}
        </h3>
        <p className="text-sm text-[var(--text-secondary)] line-clamp-2 mb-6 italic opacity-80">
          {caseItem.case_title || 'Untitled Case'}
        </p>

        <div className="space-y-3 mb-8">
          <div className="flex items-center gap-3 text-xs text-[var(--text-secondary)]">
            <div className="w-5 h-5 flex items-center justify-center rounded-md bg-[var(--surface-high)] dark:bg-neutral-800">
              <User size={12} />
            </div>
            <span className="truncate font-medium">{caseItem.primary_counsel || 'No Counsel Assigned'}</span>
          </div>
          <div className="flex items-center gap-3 text-xs text-[var(--text-secondary)]">
            <div className="w-5 h-5 flex items-center justify-center rounded-md bg-[var(--surface-high)] dark:bg-neutral-800">
              <Briefcase size={12} />
            </div>
            <span className="truncate font-medium">{caseItem.requester_department || 'General'}</span>
          </div>
          <div className="flex items-center gap-3 text-xs text-[var(--text-secondary)]">
            <div className="w-5 h-5 flex items-center justify-center rounded-md bg-[var(--surface-high)] dark:bg-neutral-800">
              <Calendar size={12} />
            </div>
            <span className="font-bold text-[var(--text-primary)]">Next: {caseItem.next_hearing_date || 'TBD'}</span>
          </div>
        </div>
      </div>

      <div className="pt-5 border-t border-[var(--border)] flex items-center justify-between text-[var(--accent)]">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
          <FileText size={16} />
          <span>Counsel AI Workspace</span>
        </div>
        <ChevronRight size={18} className="group-hover:translate-x-1.5 transition-transform" />
      </div>
    </motion.div>
  );
};

export default CaseCard;
