import { LIVINGCOLOR_FROG_URL, LIVINGCOLOR_LOGO_WHITE_URL } from '@/lib/brand-assets'
import { cn } from '@/lib/utils'

export function LivingColorLogo({
  className,
  height = 40
}: {
  className?: string
  height?: number
}) {
  return (
    <img
      alt="LivingColor"
      className={cn('w-auto object-contain object-left', className)}
      height={height}
      src={LIVINGCOLOR_LOGO_WHITE_URL}
      width={Math.round(height * 4.5)}
    />
  )
}

export function LivingColorFrog({
  className,
  size = 32
}: {
  className?: string
  size?: number
}) {
  return (
    <img
      alt="LivingColor"
      className={cn('object-contain', className)}
      height={size}
      src={LIVINGCOLOR_FROG_URL}
      width={size}
    />
  )
}

/** Sidebar header: full wordmark or frog-only when collapsed. */
export function LivingColorSidebarBrand({ collapsed = false }: { collapsed?: boolean }) {
  if (collapsed) {
    return <LivingColorFrog className="size-8" size={32} />
  }
  return <LivingColorLogo height={28} />
}
