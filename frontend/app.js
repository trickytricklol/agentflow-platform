const state = { nodes: [], edges: [], selected: null, linking: null, next: 1 };
const API = 'http://127.0.0.1:8080';
const nodesEl = document.querySelector('#nodes');
const edgesEl = document.querySelector('#edges');
const canvas = document.querySelector('#canvas');
const output = document.querySelector('#output');
const labels = { start: '开始节点', llm: '大模型节点', tool: '工具节点', agent: 'Agent 节点', end: '结束节点' };

document.querySelectorAll('[data-type]').forEach(button => button.onclick = () => addNode(button.dataset.type));
document.querySelector('#validate').onclick = validate;
document.querySelector('#export').onclick = () => { output.textContent = JSON.stringify(toDsl(), null, 2); };
document.querySelector('#save-workflow').onclick = saveWorkflow;
document.querySelector('#publish-workflow').onclick = publishWorkflow;
document.querySelector('#save').onclick = saveConfig;

function addNode(type) {
  const node = { id: `${type}-${state.next++}`, type, x: 70 + state.nodes.length * 24, y: 80 + state.nodes.length * 24, config: {} };
  state.nodes.push(node); render(); select(node.id);
}
function render() {
  nodesEl.innerHTML = '';
  state.nodes.forEach(node => {
    const el = document.createElement('div'); el.className = 'node'; el.dataset.id = node.id; el.style.left = `${node.x}px`; el.style.top = `${node.y}px`;
    el.innerHTML = `${labels[node.type]}<small>${node.id}</small>`; el.onclick = event => { event.stopPropagation(); state.linking ? connect(state.linking, node.id) : select(node.id); };
    el.onmousedown = event => drag(event, node); nodesEl.appendChild(el);
  }); drawEdges();
}
function select(id) { state.selected = id; document.querySelectorAll('.node').forEach(e => e.classList.toggle('selected', e.dataset.id === id)); const node = state.nodes.find(n => n.id === id); if (!node) return; document.querySelector('#empty').hidden = true; document.querySelector('#form').hidden = false; document.querySelector('#node-id').value = node.id; document.querySelector('#node-type').value = node.type; document.querySelector('#node-config').value = JSON.stringify(node.config, null, 2); }
function saveConfig() { const node = state.nodes.find(n => n.id === state.selected); if (!node) return; try { node.config = JSON.parse(document.querySelector('#node-config').value || '{}'); output.textContent = '配置已保存'; } catch { output.textContent = '配置必须是合法 JSON'; } }
function drag(event, node) { if (event.button !== 0) return; const rect = canvas.getBoundingClientRect(), ox = event.clientX - rect.left - node.x, oy = event.clientY - rect.top - node.y; const move = e => { node.x = Math.max(0, e.clientX - rect.left - ox); node.y = Math.max(0, e.clientY - rect.top - oy); render(); }; const up = () => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up); }; window.addEventListener('mousemove', move); window.addEventListener('mouseup', up); select(node.id); }
function connect(source, target) { if (source !== target && !state.edges.some(e => e.source === source && e.target === target)) state.edges.push({ source, target, when: 'success' }); state.linking = null; output.textContent = '连线已建立'; drawEdges(); }
function drawEdges() { edgesEl.innerHTML = ''; state.edges.forEach(edge => { const a = state.nodes.find(n => n.id === edge.source), b = state.nodes.find(n => n.id === edge.target); if (!a || !b) return; const line = document.createElementNS('http://www.w3.org/2000/svg', 'line'); line.setAttribute('x1', a.x + 65); line.setAttribute('y1', a.y + 25); line.setAttribute('x2', b.x + 65); line.setAttribute('y2', b.y + 25); line.setAttribute('stroke', '#38bdf8'); line.setAttribute('stroke-width', '2'); edgesEl.appendChild(line); }); }
function toDsl() { return { version: '1.0', nodes: state.nodes.map(({ id, type, config }) => ({ id, type, config })), edges: state.edges }; }
function validate() { const dsl = toDsl(); const starts = dsl.nodes.filter(n => n.type === 'start').length; const ends = dsl.nodes.filter(n => n.type === 'end').length; if (starts !== 1) return output.textContent = `校验失败：开始节点应为 1 个，当前 ${starts}`; if (!ends) return output.textContent = '校验失败：至少需要一个结束节点'; output.textContent = '基础校验通过，可导出 DSL'; }
async function saveWorkflow() { validate(); try { const response = await fetch(`${API}/workflows`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ name: '未命名工作流', dsl: toDsl() }) }); const data = await response.json(); if (!response.ok) throw new Error(data.error); state.workflowId = data.id; output.textContent = `已保存：${data.id}`; } catch (error) { output.textContent = `保存失败：${error.message}（请先启动后端 API）`; } }
async function publishWorkflow() { if (!state.workflowId) await saveWorkflow(); if (!state.workflowId) return; try { const published = await fetch(`${API}/workflows/${state.workflowId}/publish`, {method: 'POST'}); if (!published.ok) throw new Error((await published.json()).error); const stream = await fetch(`${API}/workflows/${state.workflowId}/run/stream`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({context: {}})}); if (!stream.ok) throw new Error((await stream.json()).error); output.textContent = '运行事件：\n'; const reader = stream.body.getReader(); const decoder = new TextDecoder(); while (true) { const {value, done} = await reader.read(); if (done) break; const chunk = decoder.decode(value); const lines = chunk.split('\\n').filter(line => line.startsWith('data: ')); lines.forEach(line => { try { output.textContent += JSON.stringify(JSON.parse(line.slice(6))) + '\\n'; } catch {} }); } } catch (error) { output.textContent = `发布/运行失败：${error.message}`; } }
canvas.onclick = () => { state.linking = state.selected; output.textContent = state.linking ? `已选择 ${state.linking}，请点击目标节点建立连线` : ''; };
addNode('start'); addNode('end'); state.edges.push({ source: state.nodes[0].id, target: state.nodes[1].id, when: 'success' }); render();
