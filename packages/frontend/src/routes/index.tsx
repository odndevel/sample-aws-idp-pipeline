import { createFileRoute, Link } from '@tanstack/react-router';
import { useState, useEffect, useCallback } from 'react';
import { useAwsClient } from '../hooks/useAwsClient';

interface Project {
  project_id: string;
  name: string;
  description: string;
  status: string;
  started_at: string;
  ended_at: string | null;
}

export const Route = createFileRoute('/')({
  component: ProjectsPage,
});

function ProjectsPage() {
  const { fetchApi } = useAwsClient();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [formData, setFormData] = useState({
    project_id: '',
    name: '',
    description: '',
  });
  const [saving, setSaving] = useState(false);

  const loadProjects = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchApi<Project[]>('projects');
      setProjects(data);
    } catch (error) {
      console.error('Failed to load projects:', error);
    }
    setLoading(false);
  }, [fetchApi]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const openCreateModal = () => {
    setEditingProject(null);
    setFormData({ project_id: '', name: '', description: '' });
    setShowModal(true);
  };

  const openEditModal = (project: Project) => {
    setEditingProject(project);
    setFormData({
      project_id: project.project_id,
      name: project.name,
      description: project.description,
    });
    setShowModal(true);
  };

  const closeModal = () => {
    setShowModal(false);
    setEditingProject(null);
    setFormData({ project_id: '', name: '', description: '' });
  };

  const handleSave = async () => {
    if (!formData.name.trim()) return;
    if (!editingProject && !formData.project_id.trim()) return;

    setSaving(true);
    try {
      if (editingProject) {
        await fetchApi<Project>(`projects/${editingProject.project_id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: formData.name,
            description: formData.description,
          }),
        });
      } else {
        await fetchApi<Project>('projects', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(formData),
        });
      }
      closeModal();
      await loadProjects();
    } catch (error) {
      console.error('Failed to save project:', error);
    }
    setSaving(false);
  };

  const handleDeleteProject = async (projectId: string) => {
    if (!window.confirm('Are you sure you want to delete this project?'))
      return;
    try {
      await fetchApi(`projects/${projectId}`, { method: 'DELETE' });
      await loadProjects();
    } catch (error) {
      console.error('Failed to delete project:', error);
    }
  };

  const formatDate = (dateString: string) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('ko-KR', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  const getProjectIcon = (index: number) => {
    const icons = [
      // Folder
      <svg
        key="folder"
        xmlns="http://www.w3.org/2000/svg"
        className="h-10 w-10"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
        />
      </svg>,
      // Chart bar
      <svg
        key="chart"
        xmlns="http://www.w3.org/2000/svg"
        className="h-10 w-10"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
        />
      </svg>,
      // Document
      <svg
        key="document"
        xmlns="http://www.w3.org/2000/svg"
        className="h-10 w-10"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>,
      // Clipboard
      <svg
        key="clipboard"
        xmlns="http://www.w3.org/2000/svg"
        className="h-10 w-10"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
        />
      </svg>,
      // Collection
      <svg
        key="collection"
        xmlns="http://www.w3.org/2000/svg"
        className="h-10 w-10"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
        />
      </svg>,
      // Briefcase
      <svg
        key="briefcase"
        xmlns="http://www.w3.org/2000/svg"
        className="h-10 w-10"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
        />
      </svg>,
      // Database
      <svg
        key="database"
        xmlns="http://www.w3.org/2000/svg"
        className="h-10 w-10"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"
        />
      </svg>,
      // Beaker
      <svg
        key="beaker"
        xmlns="http://www.w3.org/2000/svg"
        className="h-10 w-10"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"
        />
      </svg>,
    ];
    return icons[index % icons.length];
  };

  const getProjectColor = (index: number) => {
    const colors = [
      'from-blue-500 to-blue-600',
      'from-purple-500 to-purple-600',
      'from-green-500 to-green-600',
      'from-orange-500 to-orange-600',
      'from-pink-500 to-pink-600',
      'from-teal-500 to-teal-600',
      'from-indigo-500 to-indigo-600',
      'from-red-500 to-red-600',
    ];
    return colors[index % colors.length];
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <div className="flex justify-between items-center mb-6 flex-shrink-0">
        <h1 className="text-2xl font-bold text-slate-800">Projects</h1>
        <button
          onClick={openCreateModal}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <span className="text-lg">+</span>
          <span>New Project</span>
        </button>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-slate-500">Loading projects...</div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            <button
              onClick={openCreateModal}
              className="group flex flex-col items-center justify-center p-6 bg-slate-50 border-2 border-dashed border-slate-300 rounded-xl hover:border-blue-400 hover:bg-blue-50 transition-all min-h-[180px]"
            >
              <div
                className={
                  'w-12 h-12 flex items-center justify-center bg-slate-200 ' +
                  'group-hover:bg-blue-200 rounded-full mb-3 transition-colors'
                }
              >
                <span className="text-2xl text-slate-500 group-hover:text-blue-600">
                  +
                </span>
              </div>
              <span className="text-slate-600 group-hover:text-blue-600 font-medium">
                New Project
              </span>
            </button>

            {projects.map((project, index) => (
              <Link
                key={project.project_id}
                to="/projects/$projectId"
                params={{ projectId: project.project_id }}
                className="group relative bg-white border border-slate-200 rounded-xl overflow-hidden hover:shadow-lg hover:border-slate-300 transition-all"
              >
                <div
                  className={`h-24 bg-gradient-to-br ${getProjectColor(index)} flex items-center justify-center text-white/90`}
                >
                  {getProjectIcon(index)}
                </div>

                <div className="p-4">
                  <h3 className="font-semibold text-slate-800 mb-1 truncate">
                    {project.name}
                  </h3>
                  <p className="text-sm text-slate-500 mb-3 line-clamp-2 min-h-[40px]">
                    {project.description || 'No description'}
                  </p>
                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <span>{formatDate(project.started_at)}</span>
                    <span className="px-2 py-0.5 bg-slate-100 rounded-full">
                      {project.status}
                    </span>
                  </div>
                </div>

                <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-all">
                  <button
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      openEditModal(project);
                    }}
                    className="w-8 h-8 flex items-center justify-center bg-black/20 hover:bg-blue-500 text-white rounded-full"
                    title="Edit project"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-4 w-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                      />
                    </svg>
                  </button>
                  <button
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      handleDeleteProject(project.project_id);
                    }}
                    className="w-8 h-8 flex items-center justify-center bg-black/20 hover:bg-red-500 text-white rounded-full"
                    title="Delete project"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-4 w-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                      />
                    </svg>
                  </button>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-full max-w-md mx-4 shadow-2xl">
            <h2 className="text-xl font-bold text-slate-800 mb-4">
              {editingProject ? 'Edit Project' : 'Create New Project'}
            </h2>

            <div className="space-y-4">
              {!editingProject && (
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Project ID
                  </label>
                  <input
                    type="text"
                    value={formData.project_id}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        project_id: e.target.value
                          .replace(/\s/g, '_')
                          .toLowerCase(),
                      })
                    }
                    placeholder="my_project"
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                  <p className="text-xs text-slate-400 mt-1">
                    Unique identifier (no spaces)
                  </p>
                </div>
              )}

              {editingProject && (
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Project ID
                  </label>
                  <div className="px-3 py-2 bg-slate-100 border border-slate-200 rounded-lg text-slate-600">
                    {formData.project_id}
                  </div>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Project Name
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) =>
                    setFormData({ ...formData, name: e.target.value })
                  }
                  placeholder="My Project"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Description
                </label>
                <textarea
                  value={formData.description}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      description: e.target.value,
                    })
                  }
                  placeholder="Project description..."
                  rows={3}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={closeModal}
                className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={
                  !formData.name.trim() ||
                  (!editingProject && !formData.project_id.trim()) ||
                  saving
                }
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors"
              >
                {saving ? 'Saving...' : editingProject ? 'Save' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
