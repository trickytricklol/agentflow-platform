const state = { nodes: [], edges: [], selected: null, linking: null, next: 1, workflowId: null, version: 0 };
const API = location.protocol === 'file:' ? 'http://127.0.0.1:8080' : location.origin;
const nodesEl = document.querySelector('#nodes');
const edgesEl = document.querySelector('#edges');
const canvas = document.querySelector('#canvas');
const output = document.querySelector('#output');
const workflowName = document.querySelector('#workflow-name');
const tokenEl = document.querySelector('#api-token');
const runContext = document.querySelector('#run-context');
const labels = { start: '开始节点', llm: '大模型节点', tool: '工具节点', agent: 'Agent 节点', end: '结束节点' };

document.querySelectorAll('[data-type]').forEach(button => button.onclick = () => addNode(button.dataset.type));
document.querySelector('#validate').onclick = validate;
document.querySelector('#export').onclick = () => { output.textContent = JSON.stringify(toDsl(), null, 2); };
document.querySelector('#save-workflow').onclick = () => saveWorkflow();
document.querySelector('#publish-workflow').onclick = publishWorkflow;
document.querySelector('#save').onclick = saveConfig;
document.querySelector('#delete-node').onclick = deleteSelected;
document.addEventListener('keydown', event => {
  if ((event.key === 'Delete' || event.key === 'Backspace') && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) deleteSelected();
});

function authHeaders(extra = {}) {
  const token = tokenEl.value.trim();
  return token ? { ...extra, Authorization: `Bearer ${token}` } : extra;
}

async function request(path, options = {}) {
  const response = await fetch(API + path, { ...options, headers: authHeaders(options.headers || {}) });
  const type = response.headers.get('content-type') || '';
  const data = type.includes('json') ? await response.json() : await response.text();
  if (!response.ok) throw new Error(typeof data === 'string' ? data : (data.error || response.statusText));
  return data;
}

function addNode(type) {
  const node = { id: `${type}-${state.next++}`, type, x: 70 + state.nodes.length * 24, y: 80 + state.nodes.length * 24, config: {} };
  state.nodes.push(node); render(); select(node.id);
}

function render() {
  nodesEl.innerHTML = '';
  state.nodes.forEach(node => {
    const el = document.createElement('div');
    el.className = 'node';
    el.dataset.id = node.id;
    el.style.left = `${node.x}px`;
    el.style.top = `${node.y}px`;
    el.innerHTML = `${labels[node.type]}<small>${node.id}</small>`;
    el.onclick = event => { event.stopPropagation(); state.linking ? connect(state.linking, node.id) : select(node.id); };
    el.onmousedown = event => drag(event, node);
    nodesEl.appendChild(el);
  });
  drawEdges();
}

function select(id) {
  state.selected = id;
  document.querySelectorAll('.node').forEach(e => e.classList.toggle('selected', e.dataset.id === id));
  const node = state.nodes.find(n => n.id === id);
  if (!node) return;
  document.querySelector('#empty').hidden = true;
  document.querySelector('#form').hidden = false;
  document.querySelector('#node-id').value = node.id;
  document.querySelector('#node-type').value = node.type;
  document.querySelector('#node-config').value = JSON.stringify(node.config, null, 2);
}

function saveConfig() {
  const node = state.nodes.find(n => n.id === state.selected);
  if (!node) return;
  try {
    node.config = JSON.parse(document.querySelector('#node-config').value || '{}');
    output.textContent = '配置已保存';
  } catch {
    output.textContent = '配置必须是合法 JSON';
  }
}

function deleteSelected() {
  if (!state.selected) return;
  state.nodes = state.nodes.filter(node => node.id !== state.selected);
  state.edges = state.edges.filter(edge => edge.source !== state.selected && edge.target !== state.selected);
  state.selected = null;
  state.linking = null;
  document.querySelector('#form').hidden = true;
  document.querySelector('#empty').hidden = false;
  render();
  output.textContent = '节点已删除';
}

function drag(event, node) {
  if (event.button !== 0) return;
  const rect = canvas.getBoundingClientRect(), ox = event.clientX - rect.left - node.x, oy = event.clientY - rect.top - node.y;
  const move = e => {
    node.x = Math.max(0, e.clientX - rect.left - ox);
    node.y = Math.max(0, e.clientY - rect.top - oy);
    render();
  };
  const up = () => {
    window.removeEventListener('mousemove', move);
    window.removeEventListener('mouseup', up);
  };
  window.addEventListener('mousemove', move);
  window.addEventListener('mouseup', up);
  select(node.id);
}

function connect(source, target) {
  if (source !== target && !state.edges.some(edge => edge.source === source && edge.target === target)) {
    state.edges.push({ source, target, when: 'success' });
    output.textContent = '连线已建立';
  }
  state.linking = null;
  drawEdges();
}

function drawEdges() {
  edgesEl.innerHTML = '';
  state.edges.forEach(edge => {
    const a = state.nodes.find(node => node.id === edge.source), b = state.nodes.find(node => node.id === edge.target);
    if (!a || !b) return;
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', a.x + 65);
    line.setAttribute('y1', a.y + 25);
    line.setAttribute('x2', b.x + 65);
    line.setAttribute('y2', b.y + 25);
    line.setAttribute('stroke', edge.when === 'fail' ? '#f87171' : edge.when === 'always' ? '#facc15' : '#38bdf8');
    line.setAttribute('stroke-width', '2');
    edgesEl.appendChild(line);
  });
}

function toDsl() {
  return { version: '1.0', nodes: state.nodes.map(({ id, type, config }) => ({ id, type, config })), edges: state.edges };
}

function validate() {
  const dsl = toDsl();
  const starts = dsl.nodes.filter(node => node.type === 'start').length;
  const ends = dsl.nodes.filter(node => node.type === 'end').length;
  if (starts !== 1) {
    output.textContent = `校验失败：开始节点应为 1 个，当前 ${starts}`;
    return false;
  }
  if (!ends) {
    output.textContent = '校验失败：至少需要一个结束节点';
    return false;
  }
  output.textContent = '基础校验通过，保存时执行完整 DSL 校验';
  return true;
}

function readContext() {
  const raw = runContext.value.trim() || '{}';
  const parsed = JSON.parse(raw);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('运行上下文必须是 JSON 对象');
  return parsed;
}

async function saveWorkflow(silent = false) {
  if (!validate()) return null;
  const body = { name: workflowName.value.trim() || '未命名工作流', dsl: toDsl() };
  try {
    const data = state.workflowId
      ? await request(`/workflows/${state.workflowId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      : await request('/workflows', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    state.workflowId = data.id;
    state.version = data.version;
    if (!silent) output.textContent = `已保存 ${data.id} · v${data.version}${data.published ? ' · 已发布' : ' · 草稿'}`;
    return data;
  } catch (error) {
    if (!silent) output.textContent = `保存失败：${error.message}（请确认后端已启动）`;
    throw error;
  }
}

async function publishWorkflow() {
  try {
    const context = readContext();
    await saveWorkflow(true);
    const record = await request(`/workflows/${state.workflowId}/publish`, { method: 'POST' });
    state.version = record.version;
    output.textContent = `已发布 v${record.version}\n运行事件：\n`;
    const response = await fetch(`${API}/workflows/${state.workflowId}/run/stream`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ context }),
    });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || response.statusText);
    }
    await consumeStream(response);
  } catch (error) {
    output.textContent = `发布/运行失败：${error.message}`;
  }
}

async function consumeStream(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split('\n\n');
    buffer = frames.pop();
    frames.forEach(renderFrame);
  }
  if (buffer.trim()) renderFrame(buffer);
}

function renderFrame(frame) {
  let name = 'message', data = '';
  frame.split('\n').forEach(line => {
    if (line.startsWith('event:')) name = line.slice(6).trim();
    else if (line.startsWith('data:')) data += line.slice(5).trim();
  });
  if (!data) return;
  try {
    output.textContent += `${name} · ${JSON.stringify(JSON.parse(data))}\n`;
    output.scrollTop = output.scrollHeight;
  } catch {}
}

canvas.onclick = () => {
  if (!state.selected) return;
  state.linking = state.selected;
  output.textContent = `已选择 ${state.linking}，请点击目标节点建立连线`;
};

addNode('start'); addNode('end');
state.edges.push({ source: state.nodes[0].id, target: state.nodes[1].id, when: 'success' });
render();
