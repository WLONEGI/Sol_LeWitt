"use client"

import { motion, useReducedMotion } from "framer-motion"
import { cn } from "@/lib/utils"

interface WaveTextProps {
  text: string
  className?: string
  charClassName?: string
  amplitude?: number
  speed?: number
  stagger?: number
  rest?: number
}

export function WaveText({
  text,
  className,
  charClassName,
  amplitude = 6,
  speed = 0.6,
  stagger = 0.06,
  rest = 1.2,
}: WaveTextProps) {
  const prefersReducedMotion = useReducedMotion()

  return (
    <span
      className={cn("inline-flex items-center", className)}
      role="status"
      aria-live="polite"
      aria-label={text}
    >
      {text.split("").map((char, index) => {
        const duration = Math.max(0.35, speed)
        const delay = index * stagger
        return (
        <motion.span
          key={`${char}-${index}`}
          aria-hidden="true"
          className={cn("inline-block", charClassName)}
          animate={
            prefersReducedMotion
              ? { y: 0 }
              : { y: [0, -amplitude, 0] }
          }
          transition={
            prefersReducedMotion
              ? undefined
              : {
                  duration,
                  repeat: Infinity,
                  ease: "easeInOut",
                  delay,
                  repeatDelay: rest,
                }
          }
        >
          {char === " " ? "\u00A0" : char}
        </motion.span>
        )
      })}
    </span>
  )
}
