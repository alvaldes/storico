"use client"

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Zap, Table, Share2, type LucideIcon } from "lucide-react"

const iconMap: Record<string, LucideIcon> = {
  zap: Zap,
  table: Table,
  share2: Share2,
}

export interface FeatureCardData {
  title: string
  description: string
  icon: string
  color: "blue" | "green" | "orange"
}

const colorClasses: Record<FeatureCardData["color"], { bg: string; icon: string }> = {
  blue: { bg: "bg-(--color-accent-blue-bg)", icon: "text-(--color-accent-blue-icon)" },
  green: { bg: "bg-(--color-accent-green-bg)", icon: "text-(--color-accent-green-icon)" },
  orange: { bg: "bg-(--color-accent-orange-bg)", icon: "text-(--color-accent-orange-icon)" },
}

interface FeatureCardsProps {
  cards: FeatureCardData[]
}

export function FeatureCards({ cards }: FeatureCardsProps) {
  return (
    <div className="flex flex-wrap justify-center gap-6 lg:gap-8">
      {cards.map((card, index) => {
        const Icon = iconMap[card.icon]
        const colors = colorClasses[card.color]

        return (
          <Card key={index} className="w-full md:w-[calc(50%-0.75rem)] lg:w-[calc(33.333%-1.35rem)]">
            <CardHeader>
              <div className={`flex h-13 w-13 items-center justify-center rounded-xl ${colors.bg}`}>
                <Icon className={`h-6 w-6 ${colors.icon}`} />
              </div>
              <CardTitle>{card.title}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-[1.6] text-muted-foreground">
                {card.description}
              </p>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
