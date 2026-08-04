import { lazy } from 'react';
import { Navigate } from 'react-router-dom';

const AssetsManagerPage = lazy(() => import('./pages/AssetsManagerPage'));
const AuditLogPage = lazy(() => import('./pages/AuditLogPage'));
const BrowsePage = lazy(() => import('./pages/BrowsePage'));
const ClassroomPage = lazy(() => import('./pages/ClassroomPage'));
const CollectionsPage = lazy(() => import('./pages/CollectionsPage'));
const ComposePage = lazy(() => import('./pages/ComposePage'));
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const HandoutPage = lazy(() => import('./pages/HandoutPage'));
const ImportWorkbenchPage = lazy(() => import('./pages/ImportWorkbenchPage'));
const McpSettingsPage = lazy(() => import('./pages/McpSettingsPage'));
const ReviewWorkbenchPage = lazy(() => import('./pages/ReviewWorkbenchPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const SlidesPage = lazy(() => import('./pages/SlidesPage'));
const TaskCenterPage = lazy(() => import('./pages/TaskCenterPage'));
const TemplatesPage = lazy(() => import('./pages/TemplatesPage'));

export const appRoutes = [
  { path: '/', element: <DashboardPage /> },
  { path: '/dashboard', element: <DashboardPage /> },
  { path: '/browse', element: <BrowsePage /> },
  { path: '/question/new', element: <Navigate to="/browse" replace /> },
  { path: '/question/:questionId', element: <Navigate to="/browse" replace /> },
  { path: '/settings', element: <SettingsPage /> },
  { path: '/settings/mcp', element: <McpSettingsPage /> },
  { path: '/import', element: <ImportWorkbenchPage /> },
  { path: '/review', element: <ReviewWorkbenchPage /> },
  { path: '/review/:taskId', element: <ReviewWorkbenchPage /> },
  { path: '/ai-batch', element: <Navigate to="/browse" replace /> },
  { path: '/ai-chat', element: <Navigate to="/browse" replace /> },
  { path: '/basket', element: <Navigate to="/compose" replace /> },
  { path: '/compose', element: <ComposePage /> },
  { path: '/handout', element: <HandoutPage /> },
  { path: '/slides', element: <SlidesPage /> },
  { path: '/classroom', element: <ClassroomPage /> },
  { path: '/templates', element: <TemplatesPage /> },
  { path: '/assets-manager', element: <AssetsManagerPage /> },
  { path: '/collections', element: <CollectionsPage /> },
  { path: '/tasks', element: <TaskCenterPage /> },
  { path: '/task-logs', element: <Navigate to="/tasks" replace /> },
  { path: '/audit', element: <AuditLogPage /> },
] as const;
