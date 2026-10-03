import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 tracking-wide font-mono",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground hover:bg-primary/90",
        secondary: "border-border/60 bg-secondary/80 text-secondary-foreground hover:bg-secondary",
        destructive: "border-rose-500/30 bg-rose-500/10 dark:bg-rose-500/20 text-rose-600 dark:text-rose-400",
        outline: "border-border/60 text-foreground bg-background/50",
        buy: "border-emerald-500/30 bg-emerald-500/10 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 font-bold",
        sell: "border-rose-500/30 bg-rose-500/10 dark:bg-rose-500/20 text-rose-600 dark:text-rose-400 font-bold",
        success: "border-emerald-500/30 bg-emerald-500/10 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
        warning: "border-amber-500/30 bg-amber-500/10 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400",
        error: "border-rose-500/30 bg-rose-500/10 dark:bg-rose-500/20 text-rose-600 dark:text-rose-400",
        info: "border-cyan-500/30 bg-cyan-500/10 dark:bg-cyan-500/20 text-cyan-600 dark:text-cyan-400",
        neutral: "border-slate-500/30 bg-slate-500/10 dark:bg-slate-500/20 text-slate-600 dark:text-slate-300",
        terminal: "border-primary/30 bg-primary/10 text-primary font-mono",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
