import { Component, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

class ApplicationErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error) {
    console.error('页面渲染失败：', error)
  }

  render() {
    if (this.state.error) {
      return (
        <main className="fatal-error">
          <div>
            <h1>页面渲染遇到问题</h1>
            <p>{this.state.error.message || '未知前端错误'}</p>
            <button type="button" onClick={() => window.location.reload()}>重新加载页面</button>
          </div>
        </main>
      )
    }
    return this.props.children
  }
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ApplicationErrorBoundary>
      <App />
    </ApplicationErrorBoundary>
  </StrictMode>,
)
