import type { ReactNode } from 'react'

// Fixed bottom-right region for contextual information (hover descriptions, tips).
export default function InfoBox({ children }: { children: ReactNode }) {
  return <section className="info-box">{children}</section>
}
