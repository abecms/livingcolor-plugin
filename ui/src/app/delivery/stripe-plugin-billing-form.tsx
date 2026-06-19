import { useCallback, useEffect, useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { fetchPluginSettings, savePluginSettings } from '@/livingcolor'
import type { BillingConfigPayload } from '@/lib/delivery'
import { notify, notifyError } from '@/store/notifications'

import { dashboardOutlineButtonProps, dashboardPrimaryButtonProps } from './dashboard-ui'

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

export function StripePluginBillingForm() {
  const [loading, setLoading] = useState(true)
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [saveDetail, setSaveDetail] = useState<string | null>(null)
  const [configured, setConfigured] = useState(false)
  const [preview, setPreview] = useState<string | null>(null)
  const [secretInput, setSecretInput] = useState('')
  const [stripeCustomerId, setStripeCustomerId] = useState('')
  const [dailyRateEur, setDailyRateEur] = useState('')
  const [billingCurrency, setBillingCurrency] = useState('eur')
  const [invoiceMode, setInvoiceMode] = useState<'draft' | 'finalize'>('draft')
  const [billingApprovalRequired, setBillingApprovalRequired] = useState(false)
  const [maxInvoiceEur, setMaxInvoiceEur] = useState('')

  const applyBilling = useCallback((billing?: BillingConfigPayload) => {
    setStripeCustomerId(billing?.stripeCustomerId ?? '')
    setDailyRateEur(billing?.dailyRateCents != null ? String(billing.dailyRateCents / 100) : '')
    setBillingCurrency(billing?.currency ?? 'eur')
    setInvoiceMode(billing?.invoiceMode === 'finalize' ? 'finalize' : 'draft')
    setBillingApprovalRequired(Boolean(billing?.approvalRequired))
    setMaxInvoiceEur(billing?.maxInvoiceCents != null ? String(billing.maxInvoiceCents / 100) : '')
  }, [])

  const billingConfigured = useMemo(
    () => Boolean(stripeCustomerId.trim() && dailyRateEur.trim()),
    [dailyRateEur, stripeCustomerId]
  )

  const load = useCallback(async () => {
    setLoading(true)
    setSaveState('idle')
    setSaveDetail(null)
    try {
      const settings = await fetchPluginSettings()
      setConfigured(settings.stripeSecretConfigured)
      setPreview(settings.stripeSecretKeyPreview ?? null)
      setSecretInput('')
      applyBilling(settings.billing)
    } catch (error) {
      setSaveState('error')
      setSaveDetail(error instanceof Error ? error.message : 'Could not load plugin billing settings')
      notifyError(error, 'Could not load plugin billing settings')
    } finally {
      setLoading(false)
    }
  }, [applyBilling])

  useEffect(() => {
    void load()
  }, [load])

  const save = useCallback(async () => {
    if (!configured && !secretInput.trim()) {
      const message = 'Enter your Stripe secret key (sk_test_… or sk_live_…) before saving.'
      setSaveState('error')
      setSaveDetail(message)
      notifyError(new Error(message), 'Stripe secret key required')
      return
    }

    const parsedDailyRateEur = dailyRateEur.trim() ? Number.parseFloat(dailyRateEur) : null
    if (dailyRateEur.trim() && (!Number.isFinite(parsedDailyRateEur) || (parsedDailyRateEur ?? 0) <= 0)) {
      notifyError(new Error('Invalid daily rate'), 'Enter a positive daily rate')
      return
    }
    const parsedMaxInvoiceEur = maxInvoiceEur.trim() ? Number.parseFloat(maxInvoiceEur) : null
    if (maxInvoiceEur.trim() && (!Number.isFinite(parsedMaxInvoiceEur) || (parsedMaxInvoiceEur ?? 0) <= 0)) {
      notifyError(new Error('Invalid invoice cap'), 'Enter a positive max invoice amount')
      return
    }

    const billing: BillingConfigPayload = {
      stripeCustomerId: stripeCustomerId.trim() || null,
      dailyRateCents: parsedDailyRateEur != null ? Math.round(parsedDailyRateEur * 100) : null,
      currency: billingCurrency.trim().toLowerCase() || 'eur',
      invoiceMode,
      approvalRequired: billingApprovalRequired,
      maxInvoiceCents: parsedMaxInvoiceEur != null ? Math.round(parsedMaxInvoiceEur * 100) : null
    }

    setSaveState('saving')
    setSaveDetail(null)
    try {
      const settings = await savePluginSettings({
        ...(secretInput.trim() ? { stripeSecretKey: secretInput.trim() } : {}),
        billing
      })
      setConfigured(settings.stripeSecretConfigured)
      setPreview(settings.stripeSecretKeyPreview ?? null)
      setSecretInput('')
      applyBilling(settings.billing)
      setSaveState('saved')
      setSaveDetail('Settings saved to ~/.hermes/livingcolor/.')
      notify({ kind: 'success', message: 'Billing settings saved.' })
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'Could not save plugin billing settings'
      setSaveState('error')
      setSaveDetail(detail)
      notifyError(error, 'Could not save plugin billing settings')
    }
  }, [
    applyBilling,
    billingApprovalRequired,
    billingCurrency,
    configured,
    dailyRateEur,
    invoiceMode,
    maxInvoiceEur,
    secretInput,
    stripeCustomerId
  ])

  return (
    <div className="space-y-8">
      <div className="space-y-4">
        <p className="text-sm text-(--ui-text-secondary)">
          Shared by every LivingColor project. Secrets live in{' '}
          <code className="text-(--ui-text-secondary)">~/.hermes/livingcolor/.env</code>; billing
          defaults live in <code className="text-(--ui-text-secondary)">billing.json</code>.
        </p>

        {saveState === 'saved' ? (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-100">
            Saved successfully. {saveDetail}
          </div>
        ) : null}

        {saveState === 'error' && saveDetail ? (
          <div className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-100">
            {saveDetail}
          </div>
        ) : null}

        <div
          className={
            configured
              ? 'rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-100'
              : 'rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100'
          }
        >
          {configured
            ? `API key configured${preview ? ` (${preview})` : ''}.`
            : 'API key not configured — paste your sk_test_ or sk_live_ key below, then click Save.'}
        </div>

        <div className="max-w-xl space-y-2">
          <label className="text-sm font-medium" htmlFor="stripe-integration-secret-key">
            Stripe secret key
          </label>
          <Input
            autoComplete="off"
            disabled={loading || saveState === 'saving'}
            id="stripe-integration-secret-key"
            onChange={event => setSecretInput(event.target.value)}
            placeholder={preview ? 'Enter a new key to rotate' : 'sk_test_...'}
            type="password"
            value={secretInput}
          />
          <p className="text-xs text-(--ui-text-tertiary)">
            Browser autofill dots do not count — the key is only saved after you paste it and click
            Save.
          </p>
        </div>
      </div>

      <div className="space-y-4 border-t border-(--ui-border-subtle) pt-6">
        <div>
          <h3 className="text-sm font-medium text-foreground">Invoice defaults</h3>
          <p className="mt-1 text-sm text-(--ui-text-secondary)">
            Used when sprint reports create Stripe invoices (estimated days × daily rate).
          </p>
          {billingConfigured ? (
            <p className="mt-2 text-xs text-emerald-200">
              Invoice defaults configured for {stripeCustomerId.trim()}.
            </p>
          ) : null}
        </div>

        <div className="grid max-w-md gap-4">
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="stripe-customer-id">
              Stripe customer ID
            </label>
            <Input
              disabled={loading || saveState === 'saving'}
              id="stripe-customer-id"
              onChange={event => setStripeCustomerId(event.target.value)}
              placeholder="cus_..."
              value={stripeCustomerId}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="daily-rate-eur">
              Daily rate (EUR)
            </label>
            <Input
              disabled={loading || saveState === 'saving'}
              id="daily-rate-eur"
              inputMode="decimal"
              min={0}
              onChange={event => setDailyRateEur(event.target.value)}
              placeholder="800"
              step="0.01"
              type="number"
              value={dailyRateEur}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="invoice-mode">
              Invoice mode
            </label>
            <Select
              disabled={loading || saveState === 'saving' || billingApprovalRequired}
              onValueChange={value => setInvoiceMode(value === 'finalize' ? 'finalize' : 'draft')}
              value={invoiceMode}
            >
              <SelectTrigger className="h-9 rounded-md" id="invoice-mode">
                <SelectValue placeholder="Invoice mode" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="draft">Draft — review in Stripe before sending</SelectItem>
                <SelectItem value="finalize">Finalize — create a client-ready invoice</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <label className="flex items-center gap-3 text-sm">
            <Checkbox
              checked={billingApprovalRequired}
              disabled={loading || saveState === 'saving'}
              onCheckedChange={value => setBillingApprovalRequired(value === true)}
            />
            <span>Always keep invoices as drafts (manual approval)</span>
          </label>

          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="max-invoice-eur">
              Max invoice (EUR, optional)
            </label>
            <Input
              disabled={loading || saveState === 'saving'}
              id="max-invoice-eur"
              inputMode="decimal"
              min={0}
              onChange={event => setMaxInvoiceEur(event.target.value)}
              placeholder="5000"
              step="0.01"
              type="number"
              value={maxInvoiceEur}
            />
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 border-t border-(--ui-border-subtle) pt-4">
        <Button
          disabled={loading || saveState === 'saving'}
          onClick={() => void save()}
          {...dashboardPrimaryButtonProps()}
        >
          {saveState === 'saving' ? 'Saving…' : 'Save billing settings'}
        </Button>
        <Button
          disabled={loading || saveState === 'saving'}
          onClick={() => void load()}
          {...dashboardOutlineButtonProps()}
        >
          Reload
        </Button>
      </div>
    </div>
  )
}
