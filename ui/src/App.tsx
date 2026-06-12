import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import {
  ProjectIntegrationsView,
  ProjectSettingsView,
  ProjectWorkspaceLandingRedirect,
  ProjectWorkspaceLayout
} from './app/delivery'
import { ProjectDeliveryDashboardView } from './app/delivery/project-dashboard'
import { DASHBOARD_ROUTE, DELIVERY_ROUTE } from './app/routes'
import { FirebaseAuthGate } from '@/components/firebase-auth-gate'
import { FirebaseAuthProvider } from '@/contexts/firebase-auth-provider'
import { I18nProvider } from '@/i18n'

function DeliveryApp() {
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

export default function App() {
  const [apiOk, setApiOk] = useState<boolean | null>(null)
  useEffect(() => {
    const sdk = (window as any).__HERMES_PLUGIN_SDK__
    sdk.fetchJSON('/api/plugins/livingcolor/delivery/overview')
      .then(() => setApiOk(true))
      .catch(() => setApiOk(false))
  }, [])
  if (apiOk === false) {
    return (
      <div className="p-6 text-sm">
        <p className="font-medium">LivingColor backend is not mounted.</p>
        <p>Enable the plugin and restart the dashboard:</p>
        <pre className="mt-2">hermes plugins enable livingcolor</pre>
      </div>
    )
  }
  if (apiOk === null) return null
  return (
    <FirebaseAuthProvider>
      <FirebaseAuthGate>
        <DeliveryApp />
      </FirebaseAuthGate>
    </FirebaseAuthProvider>
  )
}
