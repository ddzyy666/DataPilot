async function request(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = data.detail
    const message = typeof detail === 'string' ? detail : detail?.message
    throw new Error(message || `请求失败（HTTP ${response.status}）`)
  }
  return data
}

export function submitQuery(question) {
  return request('/api/v1/query', { question })
}

export function clarifyQuery(requestId, answer) {
  return request(`/api/v1/query/${requestId}/clarify`, { answer })
}

export function confirmQuery(requestId, approved, editedSql) {
  return request(`/api/v1/query/${requestId}/confirm`, {
    approved,
    edited_sql: editedSql || null,
  })
}
