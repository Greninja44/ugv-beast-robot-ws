import { motion } from 'framer-motion'
import { Construction } from 'lucide-react'

export default function Placeholder({ name, phase }: { name: string; phase: number }) {
  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.15 }}
      className="flex h-[70vh] flex-col items-center justify-center gap-3 text-ink-dim"
    >
      <Construction size={40} strokeWidth={1.2} />
      <div className="text-lg font-medium text-ink">{name}</div>
      <div className="text-sm">Arrives in Phase {phase} of the implementation plan.</div>
    </motion.div>
  )
}
