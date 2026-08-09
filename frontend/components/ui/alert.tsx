import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const alertVariants = cva("relative w-full rounded-lg border px-4 py-3 text-sm [&>svg]:h-4 [&>svg]:w-4", {
  variants: {
    variant: {
      default: "bg-background text-foreground border-border",
      destructive: "border-destructive/30 bg-destructive/10 text-destructive",
      success: "border-success/30 bg-success/10 text-success",
    },
  },
  defaultVariants: { variant: "default" },
});

const Alert = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>
>(({ className, variant, ...props }, ref) => (
  <div ref={ref} role="alert" className={cn(alertVariants({ variant }), className)} {...props} />
));
Alert.displayName = "Alert";

const AlertDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => <p ref={ref} className={cn("leading-relaxed", className)} {...props} />
);
AlertDescription.displayName = "AlertDescription";

export { Alert, AlertDescription };
