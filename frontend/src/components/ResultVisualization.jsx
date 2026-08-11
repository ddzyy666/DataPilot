import { Component, useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
])

class ChartErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error) {
    console.error('图表渲染失败，已切换到降级视图：', error)
  }

  render() {
    if (this.state.failed) {
      return <FallbackChart result={this.props.result} />
    }
    return this.props.children
  }
}

function formatValue(value) {
  if (typeof value !== 'number') return value ?? '-'
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 4 }).format(value)
}

function EChartCanvas({ option }) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current) return undefined
    const instance = echarts.init(containerRef.current)
    instance.setOption(option)

    const resize = () => instance.resize()
    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(containerRef.current)
    window.addEventListener('resize', resize)

    return () => {
      resizeObserver.disconnect()
      window.removeEventListener('resize', resize)
      instance.dispose()
    }
  }, [option])

  return <div ref={containerRef} className="chart-container" style={{ height: 390 }} />
}

function FallbackChart({ result }) {
  const rows = Array.isArray(result?.rows) ? result.rows : []
  const xField = result?.chart?.x_field
  const yField = result?.chart?.y_fields?.[0]
  const values = rows.map((row) => Number(row?.[yField]) || 0)
  const maxValue = Math.max(...values, 1)

  if (result?.chart?.type === 'line') {
    return (
      <div className="chart-fallback-message">
        折线图组件暂时无法初始化，请查看下方按时间排序的结果明细。
      </div>
    )
  }
  if (!xField || !yField) {
    return <div className="chart-fallback-message">图表暂时无法渲染，请查看下方结果表格。</div>
  }
  return (
    <div className="fallback-chart" role="img" aria-label="查询结果降级柱状图">
      {rows.map((row, index) => (
        <div className="fallback-row" key={`${row?.[xField]}-${index}`}>
          <span className="fallback-label">{String(row?.[xField] ?? '-')}</span>
          <div className="fallback-track">
            <div className="fallback-bar" style={{ width: `${(values[index] / maxValue) * 100}%` }} />
          </div>
          <b>{formatValue(row?.[yField])}</b>
        </div>
      ))}
    </div>
  )
}

function VisualizationContent({ result }) {
  const chart = result?.chart
  const rows = Array.isArray(result?.rows) ? result.rows : []

  if (!chart || rows.length === 0) {
    return <div className="metric-visual"><div className="metric-panel"><div className="metric-label">暂无可视化数据</div></div></div>
  }

  const { type, title, x_field: xField, y_fields: yFields = [] } = chart

  if (type === 'metric') {
    const field = yFields[0]
    return (
      <div className="metric-visual">
        <div className="metric-panel">
          <div className="metric-label">{title}</div>
          <div className="metric-number">{formatValue(rows[0]?.[field])}</div>
          <div className="metric-field">{field}</div>
        </div>
      </div>
    )
  }

  if (type === 'pie') {
    const valueField = yFields[0]
    return (
      <EChartCanvas
        option={{
          color: ['#536df6', '#38bfa7', '#f5a94f', '#9a6ff2', '#e96b85', '#55a8f4'],
          tooltip: { trigger: 'item', valueFormatter: formatValue },
          legend: { bottom: 0, icon: 'circle' },
          series: [{
            name: valueField,
            type: 'pie',
            radius: ['45%', '70%'],
            center: ['50%', '46%'],
            itemStyle: { borderColor: '#fff', borderWidth: 3, borderRadius: 7 },
            label: { formatter: '{b}\n{d}%' },
            data: rows.map((row) => ({ name: row[xField], value: row[valueField] })),
          }],
        }}
      />
    )
  }

  if (type === 'table') {
    return <div className="metric-visual"><div className="metric-panel"><div className="metric-label">该结果更适合查看下方明细表格</div></div></div>
  }

  const isLine = type === 'line'
  const option = {
    color: ['#536df6', '#38bfa7', '#f5a94f'],
    tooltip: { trigger: 'axis', valueFormatter: formatValue },
    legend: { top: 4, right: 10, icon: 'roundRect' },
    grid: { top: 55, left: 58, right: 26, bottom: 55, containLabel: true },
    xAxis: {
      type: 'category',
      name: xField,
      nameLocation: 'middle',
      nameGap: 38,
      data: rows.map((row) => row[xField]),
      axisLine: { lineStyle: { color: '#dce2ee' } },
      axisTick: { show: false },
      axisLabel: { color: '#68748d', rotate: rows.length > 8 ? 28 : 0 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#edf0f5', type: 'dashed' } },
      axisLabel: { color: '#68748d' },
    },
    series: yFields.map((field) => ({
      name: field,
      type: isLine ? 'line' : 'bar',
      smooth: isLine,
      symbolSize: 8,
      showSymbol: rows.length <= 20,
      barMaxWidth: 42,
      data: rows.map((row) => row[field]),
      areaStyle: isLine ? { opacity: 0.08 } : undefined,
      itemStyle: { borderRadius: isLine ? 0 : [6, 6, 0, 0] },
    })),
  }

  return (
    <EChartCanvas option={option} />
  )
}

export default function ResultVisualization({ result }) {
  return (
    <ChartErrorBoundary result={result}>
      <VisualizationContent result={result} />
    </ChartErrorBoundary>
  )
}
