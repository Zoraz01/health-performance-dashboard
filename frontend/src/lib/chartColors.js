import { useTheme } from '../ThemeContext'

export const CHART_COLORS = {
  dark:  { axis: 'rgb(84,122,132)',  tick: 'rgb(84,122,132)',  grid: 'rgb(20,50,60)',    bg: 'rgb(6,24,29)',     ref: 'rgb(56,92,102)'  },
  light: { axis: 'rgb(118,102,82)', tick: 'rgb(118,102,82)', grid: 'rgb(178,160,136)', bg: 'rgb(252,247,238)', ref: 'rgb(118,102,82)' },
}

export function useChartColors() {
  const { isDark } = useTheme()
  return isDark ? CHART_COLORS.dark : CHART_COLORS.light
}
