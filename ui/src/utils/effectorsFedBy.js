/**
 * The effectors whose dots show a node's effect: the node itself if it is an effector,
 * otherwise every effector downstream of it (a Falloff or Gradient modifier feeding an
 * effector's strength, possibly through Math nodes). The search stops at each effector.
 */
const isEffector = node => node?.data?.nodeCategory === 'effector';

export function effectorsFedBy(startId, nodes, edges) {
  const byId = new Map(nodes.map(n => [n.id, n]));
  if (isEffector(byId.get(startId))) return [startId];
  const found = [], seen = new Set([startId]), queue = [startId];
  while (queue.length) {
    const id = queue.shift();
    for (const edge of edges) {
      if (edge.source !== id || seen.has(edge.target)) continue;
      seen.add(edge.target);
      if (isEffector(byId.get(edge.target))) found.push(edge.target);
      else queue.push(edge.target);
    }
  }
  return found;
}
