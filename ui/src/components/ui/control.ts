import { cva, type VariantProps } from 'class-variance-authority'

// Single source of truth for non-composer form-control chrome — Input,
// Textarea, and SelectTrigger all consume this. Mirrors `buttonVariants`:
// 2.5px radius, 12px text, padding-driven sizing (no fixed heights). The visual
// chrome (background, border tint, hover, focus glow, invalid state) comes from
// Hermes-native input chrome via shadcn tokens (no desktop theme override).
export const controlVariants = cva(
  'w-full min-w-0 rounded-[2.5px] border border-input bg-card text-xs leading-4 text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50',
  {
    variants: {
      size: {
        xs: 'px-2 py-0.5 text-[0.6875rem] leading-4',
        sm: 'px-2 py-1',
        default: 'px-2.5 py-1.5',
        lg: 'px-3 py-2 text-sm leading-5'
      }
    },
    defaultVariants: {
      size: 'default'
    }
  }
)

export type ControlVariantProps = VariantProps<typeof controlVariants>
