import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { fetchPluginSettings } from '@/livingcolor'
import { CreditCard } from '@/lib/icons'
import { SETTINGS_ROUTE } from '../routes'

export function StripeSetupBanner() {
  const [loading, setLoading] = useState(true)
  const [needsSetup, setNeedsSetup] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const settings = await fetchPluginSettings()
      const billing = settings.billing
      setNeedsSetup(
        !settings.stripeSecretConfigured ||
          !billing?.stripeCustomerId ||
          !billing?.dailyRateCents
      )
    } catch {
      setNeedsSetup(false)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  if (loading || !needsSetup) {
    return null
  }

  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-50">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2 font-medium text-foreground">
            <CreditCard className="size-4" />
            <span>Configure Stripe billing</span>
          </div>
          <p className="text-(--ui-text-secondary)">
            Set your Stripe API key, customer ID, and daily rate in{' '}
            <strong>Settings</strong> at the bottom of the sidebar.
          </p>
        </div>
        <Button asChild size="sm" variant="default">
          <Link to={SETTINGS_ROUTE}>Open Settings</Link>
        </Button>
      </div>
    </div>
  )
}
