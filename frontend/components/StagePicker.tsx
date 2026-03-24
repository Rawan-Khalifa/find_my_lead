"use client"

import { useState } from "react"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"
import type { PipelineStage } from "@/lib/types"

interface StagePickerProps {
  currentStage: PipelineStage
  onStageChange: (stage: PipelineStage) => void
  disabled?: boolean
  size?: "sm" | "md"
  className?: string
}

const stages: { value: PipelineStage; label: string }[] = [
  { value: "new", label: "New" },
  { value: "contacted", label: "Contacted" },
  { value: "qualified", label: "Qualified" },
  { value: "customer", label: "Customer" },
  { value: "disqualified", label: "Disqualified" },
]

function getStageColor(stage: PipelineStage): string {
  switch (stage) {
    case "new":
      return "border-gray text-muted-foreground"
    case "contacted":
      return "border-blue text-blue"
    case "qualified":
      return "border-amber text-amber"
    case "customer":
      return "border-green text-green"
    case "disqualified":
      return "border-red text-red"
    default:
      return "border-gray text-muted-foreground"
  }
}

function getStageIndicator(stage: PipelineStage): string {
  switch (stage) {
    case "new":
      return "bg-gray"
    case "contacted":
      return "bg-blue"
    case "qualified":
      return "bg-amber"
    case "customer":
      return "bg-green"
    case "disqualified":
      return "bg-red"
    default:
      return "bg-gray"
  }
}

export function StagePicker({
  currentStage,
  onStageChange,
  disabled,
  size = "md",
  className,
}: StagePickerProps) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <Select
      value={currentStage}
      onValueChange={(value) => onStageChange(value as PipelineStage)}
      disabled={disabled}
      open={isOpen}
      onOpenChange={setIsOpen}
    >
      <SelectTrigger
        className={cn(
          "border-2 bg-transparent",
          getStageColor(currentStage),
          size === "sm" ? "h-8 text-xs" : "h-9 text-sm",
          className
        )}
      >
        <div className="flex items-center gap-2">
          <div
            className={cn("h-2 w-2 rounded-full", getStageIndicator(currentStage))}
          />
          <SelectValue />
        </div>
      </SelectTrigger>
      <SelectContent className="bg-card border-border">
        {stages.map((stage) => (
          <SelectItem
            key={stage.value}
            value={stage.value}
            className="cursor-pointer"
          >
            <div className="flex items-center gap-2">
              <div
                className={cn("h-2 w-2 rounded-full", getStageIndicator(stage.value))}
              />
              {stage.label}
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
