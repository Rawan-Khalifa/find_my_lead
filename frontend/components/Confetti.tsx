"use client"

import { useEffect, useState } from "react"

interface ConfettiProps {
  active: boolean
  onComplete?: () => void
}

const CONFETTI_COLORS = ["#f59e0b", "#3b82f6", "#10b981", "#ef4444", "#8b5cf6"]

export function Confetti({ active, onComplete }: ConfettiProps) {
  const [particles, setParticles] = useState<
    Array<{ id: number; x: number; color: string; delay: number }>
  >([])

  useEffect(() => {
    if (active) {
      const newParticles = Array.from({ length: 30 }, (_, i) => ({
        id: i,
        x: Math.random() * 100,
        color: CONFETTI_COLORS[Math.floor(Math.random() * CONFETTI_COLORS.length)],
        delay: Math.random() * 0.3,
      }))
      setParticles(newParticles)

      const timer = setTimeout(() => {
        setParticles([])
        onComplete?.()
      }, 2500)

      return () => clearTimeout(timer)
    }
  }, [active, onComplete])

  if (!active || particles.length === 0) return null

  return (
    <div className="pointer-events-none fixed inset-0 z-50 overflow-hidden">
      {particles.map((particle) => (
        <div
          key={particle.id}
          className="animate-confetti absolute h-3 w-3"
          style={{
            left: `${particle.x}%`,
            backgroundColor: particle.color,
            animationDelay: `${particle.delay}s`,
            borderRadius: Math.random() > 0.5 ? "50%" : "0",
          }}
        />
      ))}
    </div>
  )
}
