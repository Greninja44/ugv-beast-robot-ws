import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Gamepad2, Activity, Map as MapIcon,
  SlidersHorizontal, ScrollText, Settings,
} from 'lucide-react'
import clsx from 'clsx'

const items = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/teleop', icon: Gamepad2, label: 'Drive' },
  { to: '/sensors', icon: Activity, label: 'Sensors' },
  { to: '/nav', icon: MapIcon, label: 'Navigation' },
  { to: '/controls', icon: SlidersHorizontal, label: 'Robot' },
  { to: '/logs', icon: ScrollText, label: 'Logs' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function Sidebar() {
  return (
    <nav className="flex md:flex-col items-center gap-1 md:gap-2 px-2 md:px-0 md:py-4
                    md:w-16 shrink-0 border-t md:border-t-0 md:border-r border-edge
                    bg-panel/60 backdrop-blur-md md:h-full
                    fixed bottom-0 inset-x-0 md:static z-20">
      <div className="hidden md:flex mb-4 h-9 w-9 items-center justify-center rounded-xl
                      bg-accent/15 text-accent font-bold text-sm">UB</div>
      {items.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          title={label}
          className={({ isActive }) =>
            clsx(
              'flex flex-1 md:flex-none items-center justify-center rounded-xl p-2.5 transition-colors',
              isActive
                ? 'bg-accent/15 text-accent'
                : 'text-ink-dim hover:text-ink hover:bg-white/5',
            )
          }
        >
          <Icon size={20} strokeWidth={1.8} />
        </NavLink>
      ))}
    </nav>
  )
}
