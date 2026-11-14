import type { DrawMode } from '../types'

const TOOLS: Record<DrawMode, { title: string; description: string; usage: string }> = {
  polygon: {
    title: 'Polígono',
    description: 'Dibuja un área de forma libre para delimitar la zona de estudio.',
    usage: 'Clic añade vértices. Doble clic, Enter o clic en el primer vértice cierra. Esc cancela.',
  },
  rectangle: {
    title: 'Rectángulo',
    description: 'Dibuja un recuadro (bbox), útil para buscar escenas NISAR. Luego puede girarse.',
    usage: 'Clic en una esquina y clic en la esquina opuesta. Esc cancela.',
  },
  region: {
    title: 'Región',
    description: 'Selecciona un país, departamento/estado o municipio según sus límites oficiales.',
    usage: 'Elige el nivel y haz clic en el mapa. Esc cancela.',
  },
}

export default function ToolInfo({ tool }: { tool: DrawMode }) {
  const { title, description, usage } = TOOLS[tool]
  return (
    <>
      <h3>{title}</h3>
      <p className="info-text">{description}</p>
      <p className="info-hint">{usage}</p>
    </>
  )
}
