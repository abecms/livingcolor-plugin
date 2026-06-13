export type ReviewRequestProvider = 'gitlab' | 'github' | string

export interface ReviewRequestFields {
  reviewRequestUrl?: string
  reviewRequestNumber?: number | null
  reviewRequestProvider?: ReviewRequestProvider
  mrUrl?: string
  mrIid?: number | null
}

export function normalizeReviewRequestProvider(value: unknown): ReviewRequestProvider {
  const raw = String(value ?? '').trim().toLowerCase()
  return raw === 'github' ? 'github' : 'gitlab'
}

export function resolveReviewRequestProvider(payload: ReviewRequestFields): ReviewRequestProvider {
  return normalizeReviewRequestProvider(payload.reviewRequestProvider)
}

export function resolveReviewRequestUrl(payload: ReviewRequestFields): string | undefined {
  const url = String(payload.reviewRequestUrl ?? payload.mrUrl ?? '').trim()
  return url || undefined
}

export function resolveReviewRequestNumber(payload: ReviewRequestFields): number | null | undefined {
  if (payload.reviewRequestNumber != null) {
    return payload.reviewRequestNumber
  }
  return payload.mrIid ?? undefined
}

export function reviewRequestShortLabel(provider?: ReviewRequestProvider): 'PR' | 'MR' {
  return normalizeReviewRequestProvider(provider) === 'github' ? 'PR' : 'MR'
}

export function reviewRequestFullLabel(provider?: ReviewRequestProvider): 'Pull Request' | 'Merge Request' {
  return normalizeReviewRequestProvider(provider) === 'github' ? 'Pull Request' : 'Merge Request'
}

export function forgeLabelForProvider(provider?: ReviewRequestProvider): 'GitHub' | 'GitLab' {
  return normalizeReviewRequestProvider(provider) === 'github' ? 'GitHub' : 'GitLab'
}

export function formatReviewRequestNumberPrefix(
  provider: ReviewRequestProvider,
  number: number | null | undefined
): string {
  if (number == null) {
    return ''
  }
  return normalizeReviewRequestProvider(provider) === 'github' ? `#${number}` : `!${number}`
}

export function formatReviewRequestLinkLabel(
  provider: ReviewRequestProvider,
  number?: number | null
): string {
  const short = reviewRequestShortLabel(provider)
  const forge = forgeLabelForProvider(provider)
  const formattedNumber = formatReviewRequestNumberPrefix(provider, number)
  if (formattedNumber) {
    return `View ${short} ${formattedNumber} on ${forge}`
  }
  return `View ${reviewRequestFullLabel(provider)} on ${forge}`
}

export function formatReviewRequestLinkLabelFr(
  provider: ReviewRequestProvider,
  number?: number | null
): string {
  const short = reviewRequestShortLabel(provider)
  const forge = forgeLabelForProvider(provider)
  const formattedNumber = formatReviewRequestNumberPrefix(provider, number)
  if (formattedNumber) {
    return `Voir la ${short} ${formattedNumber} sur ${forge}`
  }
  return `Voir la ${short} sur ${forge}`
}

export function formatReviewRequestPublicationPendingLabel(provider?: ReviewRequestProvider): string {
  const short = reviewRequestShortLabel(provider)
  return `Publication de la ${short} en cours…`
}

export function formatCodeReviewColumnTitle(provider?: ReviewRequestProvider): string {
  return `Code/${reviewRequestShortLabel(provider)}`
}

export function formatWorkOrderStageLabel(stage: string, provider?: ReviewRequestProvider): string {
  const short = reviewRequestShortLabel(provider)
  const forge = forgeLabelForProvider(provider)

  switch (stage) {
    case 'mr_draft':
      return `${short} draft`
    case 'mr_review':
      return `${short} review`
    case 'mr_publication':
      return `Publication ${forge}`
    default:
      return stage.replaceAll('_', ' ')
  }
}

export function formatGraphNodeTypeLabel(nodeType: string, provider?: ReviewRequestProvider): string {
  if (nodeType === 'mr_creation') {
    return `${reviewRequestShortLabel(provider)} draft`
  }
  return nodeType.replaceAll('_', ' ')
}
