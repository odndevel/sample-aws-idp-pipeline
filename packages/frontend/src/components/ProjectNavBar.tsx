import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { ChevronRight, Home, Settings } from 'lucide-react';
import { Project, CARD_COLORS } from './ProjectSettingsModal';

interface ProjectNavBarProps {
  project: Project;
  onSettingsClick: () => void;
}

export default function ProjectNavBar({
  project,
  onSettingsClick,
}: ProjectNavBarProps) {
  const { t } = useTranslation();
  const projectColor = CARD_COLORS[project.color ?? 0] || CARD_COLORS[0];

  return (
    <nav className="flex items-center h-[68px] min-h-[68px] flex-shrink-0 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-700 px-4 -mx-6 -mt-6 mb-3">
      {/* Breadcrumb */}
      <div className="flex items-center">
        {/* Home */}
        <Link
          to="/"
          className="inline-flex items-center justify-center h-8 w-8 rounded-md text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          title={t('projects.title')}
        >
          <Home className="h-4 w-4" />
        </Link>

        {/* Separator */}
        <ChevronRight className="h-4 w-4 text-slate-300 dark:text-slate-600 mx-0.5" />

        {/* Project */}
        <div className="flex items-center gap-2 h-8 px-2 rounded-md text-sm font-medium text-slate-800 dark:text-slate-100">
          <span
            className="w-2 h-2 rounded-full flex-shrink-0"
            style={{ background: projectColor.border }}
          />
          <span className="truncate max-w-[200px]" title={project.name}>
            {project.name}
          </span>
        </div>

        {/* Description & Owner */}
        {(project.created_by || project.description) && (
          <div className="flex flex-col justify-center ml-2 pl-3 border-l border-slate-200 dark:border-slate-700 text-xs text-slate-400 dark:text-slate-500 max-w-[400px] divide-y divide-slate-200 dark:divide-slate-700">
            {project.description && (
              <span
                className="truncate leading-tight pb-0.5"
                title={project.description}
              >
                {project.description}
              </span>
            )}
            {project.created_by && (
              <span className="truncate leading-tight pt-0.5 text-[10px]">
                {project.created_by}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Menu */}
      <div className="flex items-center gap-1">
        <button
          onClick={onSettingsClick}
          className="inline-flex items-center gap-1.5 h-8 px-3 text-sm font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 rounded-md transition-colors"
        >
          <Settings className="h-4 w-4" />
          <span>{t('nav.settings')}</span>
        </button>
      </div>
    </nav>
  );
}
