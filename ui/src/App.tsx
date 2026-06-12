import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import {
  ProjectIntegrationsView,
  ProjectSettingsView,
  ProjectWorkspaceLandingRedirect,
  ProjectWorkspaceLayout
} from './app/delivery'
import { ProjectDeliveryDashboardView } from './app/delivery/project-dashboard'
import { DASHBOARD_ROUTE, DELIVERY_ROUTE } from './app/routes'
import { I18nProvider } from '@/i18n'

export default function App() {
  return (
    <I18nProvider configClient={null}>
      <BrowserRouter basename="/livingcolor">
        <Routes>
          <Route element={<ProjectWorkspaceLandingRedirect />} index />
          <Route
            element={<ProjectWorkspaceLandingRedirect targetTab="/settings" />}
            path={DELIVERY_ROUTE.slice(1)}
          />
          <Route element={<ProjectWorkspaceLandingRedirect />} path={DASHBOARD_ROUTE.slice(1)} />
          <Route element={<ProjectWorkspaceLayout />} path="projects/:projectKey">
            <Route element={<ProjectDeliveryDashboardView />} index />
            <Route element={<ProjectSettingsView />} path="settings" />
            <Route element={<ProjectIntegrationsView />} path="integrations" />
          </Route>
          <Route element={<Navigate replace to="/" />} path="*" />
        </Routes>
      </BrowserRouter>
    </I18nProvider>
  )
}
