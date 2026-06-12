import type { ReactNode } from 'react'

import { ExternalLink } from '@/lib/external-link'

import type { GatePayloadSection } from './gate-payload-formatters'

function PayloadCard({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-black/40 p-3">
      <div className="text-xs font-medium uppercase tracking-[0.14em] text-white/45">{label}</div>
      <div className="mt-2">{children}</div>
    </div>
  )
}

function TextSection({
  label,
  preformatted,
  value
}: {
  label: string
  preformatted?: boolean
  value: string
}) {
  return (
    <PayloadCard label={label}>
      {preformatted ? (
        <pre className="whitespace-pre-wrap text-sm text-white/90">{value}</pre>
      ) : (
        <p className="text-sm text-white/90">{value}</p>
      )}
    </PayloadCard>
  )
}

function ListSection({ items, label }: { items: string[]; label: string }) {
  return (
    <PayloadCard label={label}>
      <ul className="space-y-1.5 text-sm text-white/90">
        {items.map(item => (
          <li className="flex gap-2" key={item}>
            <span className="mt-2 size-1 shrink-0 rounded-full bg-white/45" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </PayloadCard>
  )
}

function KeyValueSection({
  entries,
  label
}: {
  entries: Array<{ key: string; value: string }>
  label: string
}) {
  return (
    <PayloadCard label={label}>
      <dl className="space-y-1.5 text-sm text-white/90">
        {entries.map(entry => (
          <div className="flex gap-2" key={`${label}-${entry.key}`}>
            <dt className="shrink-0 text-white/55">{entry.key}</dt>
            <dd className="min-w-0">{entry.value}</dd>
          </div>
        ))}
      </dl>
    </PayloadCard>
  )
}

function LinkSection({ href, label, text }: { href: string; label: string; text: string }) {
  return (
    <PayloadCard label={label}>
      <ExternalLink className="text-sm text-white/90" href={href}>
        {text}
      </ExternalLink>
    </PayloadCard>
  )
}

export function GatePayloadSections({ sections }: { sections: GatePayloadSection[] }) {
  if (!sections.length) {
    return (
      <div className="rounded-lg border border-dashed border-white/10 px-4 py-6 text-center text-sm text-white/55">
        No review details available.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {sections.map(section => {
        switch (section.kind) {
          case 'text':
            return (
              <TextSection
                key={`${section.kind}-${section.label}`}
                label={section.label}
                preformatted={section.preformatted}
                value={section.value}
              />
            )
          case 'list':
            return <ListSection items={section.items} key={`${section.kind}-${section.label}`} label={section.label} />
          case 'keyValue':
            return (
              <KeyValueSection entries={section.entries} key={`${section.kind}-${section.label}`} label={section.label} />
            )
          case 'link':
            return (
              <LinkSection href={section.href} key={`${section.kind}-${section.label}`} label={section.label} text={section.text} />
            )
          default:
            return null
        }
      })}
    </div>
  )
}
