import { LivingColorLogo } from '@/components/livingcolor-logo'
import { Button } from '@/components/ui/button'

export function WelcomePage({
  onContinueLocal,
  onSignIn
}: {
  onContinueLocal: () => void
  onSignIn: () => void
}) {
  return (
    <div className="flex h-full items-center justify-center px-6 py-12">
      <div className="w-full max-w-md space-y-8 text-center">
        <LivingColorLogo className="mx-auto" height={40} />
        <p className="text-sm text-muted-foreground">
          Run delivery locally, or sign in to collaborate with your team.
        </p>
        <div className="flex flex-col gap-3">
          <Button type="button" onClick={onContinueLocal}>
            Continue locally
          </Button>
          <Button type="button" variant="outline" onClick={onSignIn}>
            Sign in to collaborate
          </Button>
        </div>
      </div>
    </div>
  )
}
