import { useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  ConfigProvider,
  Descriptions,
  Divider,
  Flex,
  Input,
  Layout,
  List,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
  theme,
} from 'antd'
import zhCN from 'antd/locale/zh_CN'
import {
  BarChartOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  CodeOutlined,
  DatabaseOutlined,
  LineChartOutlined,
  PlayCircleFilled,
  RobotOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
} from '@ant-design/icons'
import ResultVisualization from './components/ResultVisualization'
import { clarifyQuery, confirmQuery, submitQuery } from './services/api'
import './App.css'

const { Header, Content, Sider } = Layout
const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

const examples = [
  { label: '订单总数', question: '一共有多少订单？', icon: <DatabaseOutlined /> },
  {
    label: '状态分布',
    question: '按订单状态统计订单数量',
    icon: <BarChartOutlined />,
  },
  {
    label: '月度趋势',
    question: '按月份统计订单数量，月份字段命名为 order_month',
    icon: <LineChartOutlined />,
  },
]

function formatNumber(value) {
  if (typeof value !== 'number') return value ?? '-'
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 4 }).format(value)
}

function App() {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [clarificationAnswer, setClarificationAnswer] = useState('')
  const [editedSql, setEditedSql] = useState('')
  const [history, setHistory] = useState([])
  const [messageApi, contextHolder] = message.useMessage()

  const tableColumns = useMemo(
    () =>
      (result?.columns ?? []).map((column) => ({
        title: column,
        dataIndex: column,
        key: column,
        ellipsis: true,
        render: (value) => formatNumber(value),
      })),
    [result],
  )

  async function runAction(action, successMessage) {
    setLoading(true)
    try {
      const data = await action()
      setResult(data)
      setEditedSql(data.sql ?? '')
      if (data.status === 'completed') {
        setHistory((items) => [
          { question: data.question, time: new Date().toLocaleTimeString('zh-CN') },
          ...items.filter((item) => item.question !== data.question),
        ].slice(0, 6))
      }
      if (successMessage) messageApi.success(successMessage)
    } catch (error) {
      messageApi.error(error.message)
    } finally {
      setLoading(false)
    }
  }

  function handleSubmit() {
    const normalized = question.trim()
    if (!normalized) {
      messageApi.warning('请输入要分析的问题')
      return
    }
    setResult(null)
    setClarificationAnswer('')
    runAction(() => submitQuery(normalized))
  }

  function handleClarify() {
    if (!clarificationAnswer.trim()) {
      messageApi.warning('请先补充问题信息')
      return
    }
    runAction(
      () => clarifyQuery(result.request_id, clarificationAnswer.trim()),
      '补充信息已提交',
    )
  }

  function handleConfirm(approved) {
    runAction(
      () => confirmQuery(result.request_id, approved, approved ? editedSql : null),
      approved ? 'SQL 已批准执行' : '已拒绝执行',
    )
  }

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#4f6ef7',
          borderRadius: 12,
          colorBgLayout: '#f3f6fb',
          fontFamily: "Inter, 'Microsoft YaHei', system-ui, sans-serif",
        },
      }}
    >
      {contextHolder}
      <Layout className="app-shell">
        <Sider width={248} className="app-sider" breakpoint="lg" collapsedWidth="0">
          <div className="brand">
            <div className="brand-mark"><RobotOutlined /></div>
            <div>
              <div className="brand-name">DataPilot</div>
              <div className="brand-caption">智能数据分析助手</div>
            </div>
          </div>

          <div className="sider-section">
            <Text className="sider-label">快捷提问</Text>
            <Space direction="vertical" size={8} className="example-list">
              {examples.map((example) => (
                <button
                  className="example-button"
                  key={example.label}
                  onClick={() => setQuestion(example.question)}
                >
                  {example.icon}<span>{example.label}</span>
                </button>
              ))}
            </Space>
          </div>

          <div className="sider-section history-section">
            <Text className="sider-label">最近分析</Text>
            {history.length === 0 ? (
              <div className="empty-history">完成一次查询后将在这里显示</div>
            ) : (
              <List
                dataSource={history}
                split={false}
                renderItem={(item) => (
                  <List.Item className="history-item" onClick={() => setQuestion(item.question)}>
                    <div className="history-question">{item.question}</div>
                    <div className="history-time">{item.time}</div>
                  </List.Item>
                )}
              />
            )}
          </div>

          <div className="sider-status">
            <span className="status-dot" />
            Agent 服务已连接
          </div>
        </Sider>

        <Layout>
          <Header className="app-header">
            <div>
              <Title level={4}>数据分析工作台</Title>
              <Text type="secondary">用自然语言查询企业数据</Text>
            </div>
            <Space>
              <Tag icon={<SafetyCertificateOutlined />} color="green">只读安全查询</Tag>
              <Tag icon={<CheckCircleFilled />} color="blue">LangGraph</Tag>
            </Space>
          </Header>

          <Content className="app-content">
            <section className="query-hero">
              <div className="eyebrow"><RobotOutlined /> TEXT-TO-SQL AGENT</div>
              <Title>今天想从数据里了解什么？</Title>
              <Paragraph></Paragraph>
              <div className="query-box">
                <TextArea
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onPressEnter={(event) => {
                    if (!event.shiftKey) {
                      event.preventDefault()
                      handleSubmit()
                    }
                  }}
                  placeholder="例如：按订单状态统计订单数量"
                  autoSize={{ minRows: 2, maxRows: 5 }}
                  disabled={loading}
                />
                <Button
                  type="primary"
                  size="large"
                  icon={<SendOutlined />}
                  loading={loading}
                  onClick={handleSubmit}
                >
                  开始分析
                </Button>
              </div>
              <Text type="secondary" className="query-tip">按 Enter 提交，Shift + Enter 换行</Text>
            </section>

            {result?.status === 'waiting_for_clarification' && (
              <Card className="action-card clarification-card" title="Agent 需要你补充一个信息">
                <Title level={4}>{result.clarification_question}</Title>
                <Flex gap={8} wrap="wrap" className="option-row">
                  {(result.clarification_options ?? []).map((option) => (
                    <Button key={option} onClick={() => setClarificationAnswer(option)}>{option}</Button>
                  ))}
                </Flex>
                <Space.Compact block>
                  <Input
                    value={clarificationAnswer}
                    onChange={(event) => setClarificationAnswer(event.target.value)}
                    placeholder="输入补充说明"
                    onPressEnter={handleClarify}
                  />
                  <Button type="primary" loading={loading} onClick={handleClarify}>继续分析</Button>
                </Space.Compact>
              </Card>
            )}

            {result?.status === 'waiting_for_confirmation' && (
              <Card className="action-card approval-card" title="高风险 SQL 等待人工确认">
                <Alert
                  type="warning"
                  showIcon
                  message={result.risk_reasons?.join('；') || '该查询被判断为高风险'}
                  description="请检查 SQL。你可以直接批准、修改后批准，或者拒绝执行。"
                />
                <TextArea
                  className="sql-editor"
                  value={editedSql}
                  onChange={(event) => setEditedSql(event.target.value)}
                  autoSize={{ minRows: 5, maxRows: 12 }}
                />
                <Flex justify="flex-end" gap={12}>
                  <Button danger onClick={() => handleConfirm(false)} disabled={loading}>拒绝执行</Button>
                  <Button type="primary" loading={loading} onClick={() => handleConfirm(true)}>批准并执行</Button>
                </Flex>
              </Card>
            )}

            {result?.status === 'rejected' && (
              <Alert className="result-alert" type="info" showIcon message="该查询已被拒绝，SQL 未执行。" />
            )}

            {result?.status === 'completed' && (
              <div className="result-stack">
                <Row gutter={[16, 16]}>
                  <Col xs={24} sm={12} xl={6}>
                    <Card className="stat-card"><Statistic title="返回行数" value={result.row_count} suffix="行" /></Card>
                  </Col>
                  <Col xs={24} sm={12} xl={6}>
                    <Card className="stat-card"><Statistic title="总耗时" value={result.timings?.total_ms ?? 0} precision={2} suffix="ms" prefix={<ClockCircleOutlined />} /></Card>
                  </Col>
                  <Col xs={24} sm={12} xl={6}>
                    <Card className="stat-card"><Statistic title="模型耗时" value={result.timings?.llm_total_ms ?? 0} precision={2} suffix="ms" /></Card>
                  </Col>
                  <Col xs={24} sm={12} xl={6}>
                    <Card className="stat-card"><Statistic title="SQL执行" value={result.timings?.sql_execution_ms ?? 0} precision={2} suffix="ms" /></Card>
                  </Col>
                </Row>

                <Card className="insight-card">
                  <div className="section-heading">
                    <div className="section-icon insight-icon"><RobotOutlined /></div>
                    <div><Title level={4}>分析结论</Title><Text type="secondary">基于查询结果自动生成</Text></div>
                  </div>
                  <Paragraph className="summary-text">{result.result_summary || '查询已完成。'}</Paragraph>
                  {result.insights?.length > 0 && (
                    <div className="insight-list">
                      {result.insights.map((insight, index) => (
                        <div className="insight-item" key={`${insight}-${index}`}>
                          <span>{index + 1}</span>{insight}
                        </div>
                      ))}
                    </div>
                  )}
                  {result.result_analysis_error && (
                    <Alert type="warning" showIcon message="中文总结已降级" description={result.result_analysis_error} />
                  )}
                </Card>

                <Card className="visual-card">
                  <div className="section-heading">
                    <div className="section-icon chart-icon"><BarChartOutlined /></div>
                    <div><Title level={4}>数据可视化</Title><Text type="secondary">{result.chart?.reason || '根据结果结构自动选择展示方式'}</Text></div>
                  </div>
                  <ResultVisualization result={result} />
                </Card>

                <Row gutter={[16, 16]}>
                  <Col xs={24} xl={15}>
                    <Card title="查询结果明细" className="detail-card">
                      <Table
                        columns={tableColumns}
                        dataSource={(result.rows ?? []).map((row, index) => ({ ...row, __key: index }))}
                        rowKey="__key"
                        pagination={{ pageSize: 8, showSizeChanger: false }}
                        scroll={{ x: true }}
                        size="middle"
                      />
                    </Card>
                  </Col>
                  <Col xs={24} xl={9}>
                    <Card title="数据画像" className="detail-card profile-card">
                      <Descriptions column={1} size="small" bordered>
                        <Descriptions.Item label="数据行数">{result.data_profile?.row_count ?? 0}</Descriptions.Item>
                        <Descriptions.Item label="字段数量">{result.data_profile?.columns?.length ?? 0}</Descriptions.Item>
                        <Descriptions.Item label="是否截断">{result.data_profile?.truncated ? '是' : '否'}</Descriptions.Item>
                      </Descriptions>
                      <Divider orientation="left" plain>数值统计</Divider>
                      {Object.entries(result.data_profile?.numeric_summary ?? {}).length === 0 ? (
                        <Text type="secondary">没有可统计的数值字段</Text>
                      ) : Object.entries(result.data_profile.numeric_summary).map(([field, stats]) => (
                        <div className="profile-metric" key={field}>
                          <Text strong>{field}</Text>
                          <div className="profile-grid">
                            <span>最小值 <b>{formatNumber(stats.min)}</b></span>
                            <span>最大值 <b>{formatNumber(stats.max)}</b></span>
                            <span>合计 <b>{formatNumber(stats.sum)}</b></span>
                            <span>平均 <b>{formatNumber(stats.average)}</b></span>
                          </div>
                        </div>
                      ))}
                    </Card>
                  </Col>
                </Row>

                <Card className="sql-card" title={<Space><CodeOutlined />生成并执行的 SQL</Space>}>
                  <pre>{result.sql}</pre>
                  <Flex gap={8} wrap="wrap">
                    <Tag color={result.risk_level === 'high' ? 'red' : result.risk_level === 'medium' ? 'orange' : 'green'}>
                      {result.risk_level?.toUpperCase()} RISK
                    </Tag>
                    {result.reviewed && <Tag color="blue">已语义审核</Tag>}
                    {result.was_repaired && <Tag color="purple">已自动修复</Tag>}
                  </Flex>
                </Card>
              </div>
            )}

            {!result && !loading && (
              <div className="empty-state">
                <PlayCircleFilled />
                <Title level={4}>选择一个示例或输入你的问题</Title>
                <Text type="secondary">分析完成后，图表和数据洞察会显示在这里</Text>
              </div>
            )}
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  )
}

export default App
