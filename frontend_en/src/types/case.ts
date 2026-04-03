/**
 * LawNidhi Integration — Case Portfolio Types
 */

export type CaseStatus = 'NEW' | 'ACTIVE' | 'PENDING' | 'CLOSED' | 'DISPOSED' | 'APPEAL';

export interface Case {
  id: number;
  case_number: string;
  case_year: string;
  case_title?: string;
  status: CaseStatus | string;
  primary_counsel?: string;
  associate_counsel?: string;
  applicant?: string;
  respondent?: string;
  requester_department?: string;
  requester_name?: string;
  diary_number?: string;
  date_assigned?: string;
  date_closed?: string;
  notes?: string;
  created_at?: string;
  updated_at?: string;
  notebook_id?: string;
  last_hearing_date?: string;
  next_hearing_date?: string;
}

export interface CaseDocument {
  name: string;
  path?: string;
  local_path?: string;
  storage_path?: string;
  type: 'order' | 'cause_list' | 'upload' | 'document' | string;
  date?: string;
  size?: number;
  url?: string;
  status?: 'imported' | 'available' | string;
}
