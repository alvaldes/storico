"use client"

import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/accordion"

export interface FaqItem {
  question: string
  answer: string
}

interface FaqAccordionProps {
  items: FaqItem[]
}

export function FaqAccordion({ items }: FaqAccordionProps) {
  return (
    <div className="w-full max-w-3xl rounded-2xl border border-border bg-card shadow-card">
      <Accordion className="divide-y divide-border">
        {items.map((item, index) => (
          <AccordionItem
            key={index}
            className={index === 0 ? "rounded-t-2xl" : index === items.length - 1 ? "rounded-b-2xl" : ""}
          >
            <AccordionTrigger className="px-6 py-5 md:px-8 md:py-6">
              {item.question}
            </AccordionTrigger>
            <AccordionContent className="px-6 pb-5 md:px-8 md:pb-6">
              {item.answer}
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  )
}
