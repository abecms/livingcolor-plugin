import { ManagerPageHeader, ManagerPageShell, ManagerSection } from '../manager-page-layout'

import { Settings } from '@/lib/icons'

import { StripePluginBillingForm } from './stripe-plugin-billing-form'

export function PluginSettingsView() {
  return (
    <ManagerPageShell wide={false}>
      <ManagerPageHeader
        description="Global LivingColor settings shared by every project."
        eyebrow="LivingColor"
        icon={Settings}
        title="Settings"
      />

      <ManagerSection icon={Settings} title="Stripe billing">
        <div className="p-4">
          <StripePluginBillingForm />
        </div>
      </ManagerSection>
    </ManagerPageShell>
  )
}
