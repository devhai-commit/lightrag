// GraphKnowledge.jsx - Knowledge Graph visualization (renamed from Knowledge.jsx)
// This file contains the original Knowledge graph visualization
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import ForceGraph2D from 'react-force-graph-2d';
import {
    BookOpen, Database, ChevronDown, AlertTriangle,
    Link as LinkIcon, Hash, Search, Loader2, Maximize2, ZoomIn, ZoomOut,
    Brain, X
} from 'lucide-react';
import { workspacesApi, ragGraphApi } from '../utils/api';

// ─── Reasoning path helpers (BFS over the already-fetched graph) ──────────────
function buildAdjacency(links) {
    const adj = new Map();
    const add = (a, b, link) => {
        if (!adj.has(a)) adj.set(a, []);
        adj.get(a).push({ to: b, link });
    };
    links.forEach(l => {
        const s = typeof l.source === 'object' ? l.source.id : l.source;
        const t = typeof l.target === 'object' ? l.target.id : l.target;
        add(s, t, l);
        add(t, s, l);
    });
    return adj;
}

function bfsPath(adj, startId, endId) {
    if (startId === endId) return { nodeIds: [startId], links: [] };
    const visited = new Set([startId]);
    const queue = [[startId, [], []]];
    while (queue.length) {
        const [cur, nodePath, linkPath] = queue.shift();
        for (const { to, link } of (adj.get(cur) || [])) {
            if (visited.has(to)) continue;
            if (to === endId) return { nodeIds: [startId, ...nodePath, to], links: [...linkPath, link] };
            visited.add(to);
            queue.push([to, [...nodePath, to], [...linkPath, link]]);
        }
    }
    return null;
}

function computeReasoningPath(nodes, links, entityNames) {
    const nodeById = new Map(nodes.map(n => [n.id, n]));
    const norm = (s) => s.trim().toLowerCase();
    const idByNorm = new Map(nodes.map(n => [norm(n.id), n.id]));

    const matched = [];
    const missing = [];
    entityNames.forEach(name => {
        if (nodeById.has(name)) matched.push(name);
        else if (idByNorm.has(norm(name))) matched.push(idByNorm.get(norm(name)));
        else missing.push(name);
    });

    const uniqueMatched = [...new Set(matched)];
    const pathNodeIds = new Set(uniqueMatched);
    const pathLinkSet = new Set();

    if (uniqueMatched.length >= 2) {
        const adj = buildAdjacency(links);
        for (let i = 0; i < uniqueMatched.length - 1; i++) {
            const res = bfsPath(adj, uniqueMatched[i], uniqueMatched[i + 1]);
            if (res) {
                res.nodeIds.forEach(id => pathNodeIds.add(id));
                res.links.forEach(l => pathLinkSet.add(l));
            }
        }
    }

    const pathNodeSet = new Set([...pathNodeIds].map(id => nodeById.get(id)).filter(Boolean));
    return { pathNodes: pathNodeSet, pathLinks: pathLinkSet, missing };
}

const ENTITY_COLORS = {
    Person: '#3b82f6',       // Blue
    Organization: '#22c55e', // Green
    Location: '#eab308',     // Yellow
    Event: '#f97316',        // Orange
    Concept: '#a855f7',      // Purple
    Date: '#ef4444',         // Red
    Technology: '#ec4899',   // Pink
    Method: '#06b6d4',       // Cyan
    Dataset: '#8b5cf6',      // Violet
    Product: '#14b8a6',      // Teal
    Article: '#f43f5e',      // Rose
    Industry: '#84cc16',     // Lime
    Unknown: '#9ca3af'       // Gray
};

export default function GraphKnowledge() {
    const [searchParams, setSearchParams] = useSearchParams();
    const urlWsId = searchParams.get('ws');
    const urlEntities = useMemo(() => {
        const raw = searchParams.get('entities');
        return raw ? raw.split(',').map(s => s.trim()).filter(Boolean) : [];
    }, [searchParams]);

    const [workspaces, setWorkspaces] = useState([]);
    const [selectedWs, setSelectedWs] = useState(null);
    const [showWsDropdown, setShowWsDropdown] = useState(false);

    // Reasoning path (from a chat citation → "Xem đường đi trên đồ thị")
    const [pathNodes, setPathNodes] = useState(new Set());
    const [pathLinks, setPathLinks] = useState(new Set());
    const [pathMissing, setPathMissing] = useState([]);
    const pathActive = pathNodes.size > 0 || pathMissing.length > 0;

    const clearPath = useCallback(() => {
        setPathNodes(new Set());
        setPathLinks(new Set());
        setPathMissing([]);
        setSearchParams(prev => {
            const next = new URLSearchParams(prev);
            next.delete('entities');
            return next;
        });
    }, [setSearchParams]);

    const [graphData, setGraphData] = useState({ nodes: [], links: [] });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [windowSize, setWindowSize] = useState({ width: 800, height: 600 });
    const containerRef = useRef(null);
    const fgRef = useRef();

    // ─── Theme Observer ─────────────────────────────────────────────────────
    const [isDarkMode, setIsDarkMode] = useState(() => document.documentElement.classList.contains('dark'));

    useEffect(() => {
        const observer = new MutationObserver(() => {
            setIsDarkMode(document.documentElement.classList.contains('dark'));
        });
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
        return () => observer.disconnect();
    }, []);

    // ─── Fetch Workspaces ──────────────────────────────────────────────────
    useEffect(() => {
        workspacesApi.list()
            .then(res => res.ok ? res.json() : [])
            .then(data => {
                setWorkspaces(data);
                if (data.length > 0) {
                    const fromUrl = urlWsId ? data.find(ws => String(ws.id) === urlWsId) : null;
                    setSelectedWs(fromUrl || data[0]);
                }
            })
            .catch(() => {});
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // ─── Responsive Graph Container ─────────────────────────────────────────
    useEffect(() => {
        const updateSize = () => {
            if (containerRef.current) {
                setWindowSize({
                    width: containerRef.current.clientWidth,
                    height: containerRef.current.clientHeight
                });
            }
        };
        updateSize();
        window.addEventListener('resize', updateSize);
        return () => window.removeEventListener('resize', updateSize);
    }, []);

    // ─── Fetch Graph Data ───────────────────────────────────────────────────
    useEffect(() => {
        if (!selectedWs) return;

        let isMounted = true;
        setLoading(true);
        setError(null);
        setGraphData({ nodes: [], links: [] });

        ragGraphApi.getGraph(selectedWs.id)
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(data => {
                if (!isMounted) return;

                const nodes = (data.nodes || []).map(entry => ({
                    id: entry.id,
                    name: entry.label,
                    type: entry.entity_type || 'Unknown',
                    description: entry.description || '',
                    val: entry.degree ? Math.max(1, Math.min(entry.degree / 2, 20)) : 1,
                    rawDegree: entry.degree || 0,
                    color: ENTITY_COLORS[entry.entity_type] || ENTITY_COLORS.Unknown
                }));

                const links = (data.edges || []).map(edge => ({
                    source: edge.source,
                    target: edge.target,
                    name: edge.label,
                    description: edge.description || '',
                    keywords: edge.keywords || '',
                    weight: edge.weight || 1
                }));

                const nodeIds = new Set(nodes.map(n => n.id));
                const validLinks = links.filter(l => nodeIds.has(l.source) && nodeIds.has(l.target));

                const graph = { nodes, links: validLinks };

                setGraphData(graph);

                setTimeout(() => {
                    if (fgRef.current && isMounted) {
                         fgRef.current.zoomToFit(400, 50);
                    }
                }, 500);

            })
            .catch(err => {
                if (!isMounted) return;
                setError("Không thể lấy sơ đồ tri thức. " + err.message);
            })
            .finally(() => {
                if (isMounted) setLoading(false);
            });

        return () => { isMounted = false; };
    }, [selectedWs]);

    // ─── Reasoning Path (entities passed in from a chat citation) ──────────────
    useEffect(() => {
        if (graphData.nodes.length === 0 || urlEntities.length === 0) return;

        const { pathNodes: pNodes, pathLinks: pLinks, missing } = computeReasoningPath(
            graphData.nodes, graphData.links, urlEntities
        );
        setPathNodes(pNodes);
        setPathLinks(pLinks);
        setPathMissing(missing);

        if (pNodes.size > 0) {
            setTimeout(() => {
                if (fgRef.current) {
                    fgRef.current.zoomToFit(600, 100, n => pNodes.has(n));
                }
            }, 600);
        }
    }, [graphData, urlEntities]);

    // ─── Calculate Legends & Stats ──────────────────────────────────────────
    const stats = useMemo(() => {
        const typeCount = {};
        const sortedEntities = [...graphData.nodes].sort((a, b) => b.rawDegree - a.rawDegree).slice(0, 10);

        graphData.nodes.forEach(n => {
            typeCount[n.type] = (typeCount[n.type] || 0) + 1;
        });

        const legendItems = Object.entries(typeCount)
            .sort((a, b) => b[1] - a[1])
            .map(([type, count]) => ({
                type,
                count,
                color: ENTITY_COLORS[type] || ENTITY_COLORS.Unknown
            }));

        return { legendItems, topEntities: sortedEntities, totalNodes: graphData.nodes.length, totalLinks: graphData.links.length };
    }, [graphData]);

    // ─── Tweak Physics ──────────────────────────────────────────────────────
    useEffect(() => {
        if (fgRef.current && graphData.nodes.length > 0) {
            fgRef.current.d3Force('charge').strength(-180).distanceMax(600);
            fgRef.current.d3Force('link').distance(70);
        }
    }, [graphData]);

    // ─── Graph Interaction ──────────────────────────────────────────────────
    const [highlightNodes, setHighlightNodes] = useState(new Set());
    const [highlightLinks, setHighlightLinks] = useState(new Set());
    const [hoverNode, setHoverNode] = useState(null);

    const handleNodeHover = useCallback(node => {
        setHighlightNodes(new Set());
        setHighlightLinks(new Set());

        if (node) {
            const hNodes = new Set();
            const hLinks = new Set();
            hNodes.add(node);

            graphData.links.forEach(link => {
                if (link.source.id === node.id || link.target.id === node.id) {
                    hLinks.add(link);
                    hNodes.add(link.source);
                    hNodes.add(link.target);
                }
            });

            setHighlightNodes(hNodes);
            setHighlightLinks(hLinks);
        }

        setHoverNode(node || null);
    }, [graphData]);

    const handleNodeClick = useCallback(node => {
        if (fgRef.current && node) {
            fgRef.current.centerAt(node.x, node.y, 1000);
            fgRef.current.zoom(4, 1000);
        }
    }, []);

    // Paint node — combines hover highlight (grey/dim) with the pinned reasoning
    // path highlight (amber/gold), which takes visual priority when active.
    const paintNode = useCallback((node, ctx, globalScale) => {
        const isHovered = highlightNodes.has(node);
        const isOnPath = pathNodes.has(node);
        const isEmphasized = isHovered || isOnPath;
        const dimOthers = pathActive ? pathNodes.size > 0 : highlightNodes.size > 0;
        const radius = Math.sqrt(node.val) * 4;

        if (hoverNode === node) {
            ctx.beginPath();
            ctx.arc(node.x, node.y, radius + 3, 0, 2 * Math.PI, false);
            ctx.fillStyle = node.color;
            ctx.globalAlpha = 0.3;
            ctx.fill();
            ctx.globalAlpha = 1;
        }

        if (isOnPath) {
            ctx.beginPath();
            ctx.arc(node.x, node.y, radius + 4, 0, 2 * Math.PI, false);
            ctx.strokeStyle = '#f59e0b';
            ctx.lineWidth = 2.5 / globalScale;
            ctx.stroke();
        }

        ctx.beginPath();
        ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
        ctx.fillStyle = dimOthers && !isEmphasized ? 'rgba(150,150,150,0.1)' : (isOnPath ? '#f59e0b' : node.color);
        ctx.fill();

        if (!dimOthers || isEmphasized) {
            ctx.strokeStyle = isDarkMode ? '#111827' : '#ffffff';
            ctx.lineWidth = 1 / globalScale;
            ctx.stroke();
        }

        if (globalScale > 1.5 || isEmphasized) {
            const label = node.name;
            const fontSize = isEmphasized ? 12/globalScale : 11/globalScale;
            ctx.font = `${fontSize}px Inter, sans-serif`;

            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';

            if (dimOthers && !isEmphasized) {
                ctx.fillStyle = isDarkMode ? 'rgba(150,150,150,0.3)' : 'rgba(156, 163, 175, 0.4)';
            } else {
                ctx.fillStyle = isDarkMode ? 'rgba(255, 255, 255, 0.85)' : 'rgba(17, 24, 39, 0.85)';
            }

            ctx.fillText(label, node.x, node.y + radius + (8 / globalScale));
        }
    }, [hoverNode, highlightNodes, isDarkMode, pathNodes, pathActive]);

    // Paint Link — reasoning-path edges draw thick amber, hover edges grey.
    // Drawn as a straight line, so linkCurvature must stay 0 — otherwise the
    // library's invisible hover hit-path (which follows the curvature setting)
    // no longer lines up with what's actually rendered here.
    const paintLink = useCallback((link, ctx, globalScale) => {
        const isHovered = highlightLinks.has(link);
        const isOnPath = pathLinks.has(link);

        ctx.beginPath();
        ctx.moveTo(link.source.x, link.source.y);
        ctx.lineTo(link.target.x, link.target.y);

        if (isOnPath) {
            ctx.strokeStyle = '#f59e0b';
            ctx.lineWidth = 3 / globalScale;
        } else if (isHovered) {
            ctx.strokeStyle = isDarkMode ? 'rgba(156, 163, 175, 0.8)' : 'rgba(75, 85, 99, 0.8)';
            ctx.lineWidth = 2 / globalScale;
        } else {
            ctx.strokeStyle = isDarkMode ? 'rgba(55, 65, 81, 0.4)' : 'rgba(209, 213, 219, 0.7)';
            ctx.lineWidth = 1 / globalScale;
        }
        ctx.stroke();
    }, [highlightLinks, isDarkMode, pathLinks]);

    // Widens the invisible hover/click target for links beyond their thin
    // rendered stroke, so hovering near a (straight) edge reliably registers.
    const paintLinkPointerArea = useCallback((link, color, ctx) => {
        ctx.beginPath();
        ctx.moveTo(link.source.x, link.source.y);
        ctx.lineTo(link.target.x, link.target.y);
        ctx.strokeStyle = color;
        ctx.lineWidth = 8;
        ctx.stroke();
    }, []);


    return (
        <div className="flex flex-col h-full bg-white dark:bg-gray-900 overflow-hidden relative p-2 lg:p-3 gap-3">

            {/* Top Bar */}
            <div className="bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-2 flex items-center justify-between shrink-0 shadow-sm">
                <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-sm">
                        <BookOpen className="w-4 h-4 text-white" />
                    </div>
                    <h1 className="text-sm font-bold text-gray-900 dark:text-white tracking-wide">Đồ thị tri thức</h1>
                </div>

                <div className="flex items-center gap-3">
                    {/* Workspace Selector */}
                    <div className="relative">
                        <button
                            onClick={() => setShowWsDropdown(v => !v)}
                            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors min-w-[180px] shadow-sm"
                        >
                            <Database className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                            <span className="truncate flex-1 text-left font-medium">{selectedWs?.name || 'Chọn Workspace'}</span>
                            <ChevronDown className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                        </button>
                        {showWsDropdown && (
                            <div className="absolute top-full right-0 mt-1 w-60 bg-white dark:bg-gray-900 rounded-xl shadow-xl border border-gray-200 dark:border-gray-800 z-50 overflow-hidden">
                                {workspaces.length === 0 ? (
                                    <p className="text-xs text-gray-500 px-4 py-3">Chưa có workspace</p>
                                ) : workspaces.map(ws => (
                                    <button
                                        key={ws.id}
                                        onClick={() => { setSelectedWs(ws); setShowWsDropdown(false); }}
                                        className={`w-full flex items-center gap-3 px-3 py-2.5 text-xs transition-colors ${
                                            selectedWs?.id === ws.id
                                                ? 'bg-primary-50 dark:bg-primary-500/10 text-primary-700 dark:text-primary-400'
                                                : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-200'
                                        }`}
                                    >
                                        <Database className={`w-3.5 h-3.5 flex-shrink-0 ${selectedWs?.id === ws.id ? 'text-primary-500 opacity-100' : 'opacity-60'}`} />
                                        <span className="flex-1 truncate text-left">{ws.name}</span>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Graph Area */}
            <div className="flex-1 relative flex bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden shadow-sm" ref={containerRef}>
                {loading ? (
                    <div className="absolute inset-0 flex flex-col items-center justify-center bg-white/80 dark:bg-gray-950/80 backdrop-blur-sm z-20">
                        <Loader2 className="w-8 h-8 text-primary-500 animate-spin mb-3" />
                        <p className="text-gray-600 dark:text-gray-400 font-medium text-sm">Đang trích xuất đồ thị tri thức...</p>
                    </div>
                ) : error ? (
                    <div className="absolute inset-0 flex flex-col items-center justify-center z-20">
                        <div className="w-14 h-14 rounded-2xl bg-red-50 dark:bg-red-500/10 flex items-center justify-center mb-3">
                            <AlertTriangle className="w-6 h-6 text-red-500" />
                        </div>
                        <p className="text-gray-500 dark:text-gray-400 max-w-md text-center text-sm">{error}</p>
                    </div>
                ) : graphData.nodes.length === 0 ? (
                    <div className="absolute inset-0 flex flex-col items-center justify-center z-20">
                        <Database className="w-10 h-10 text-gray-300 dark:text-gray-700 mb-3" />
                        <p className="text-gray-500 dark:text-gray-400 text-sm font-medium">Chưa có dữ liệu đồ thị tri thức cho workspace này.</p>
                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Vui lòng upload tài liệu và xử lý RAG.</p>
                    </div>
                ) : (
                    <>
                        {/* Main Graph Component */}
                        <ForceGraph2D
                            ref={fgRef}
                            width={windowSize.width}
                            height={windowSize.height}
                            graphData={graphData}
                            nodeLabel={node => `<div class="bg-white/95 dark:bg-gray-900/95 text-gray-900 dark:text-white px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 shadow-xl backdrop-blur-md font-sans text-xs max-w-xs">
                                <div class="font-bold mb-0.5">${node.name}</div>
                                <div class="flex items-center gap-1.5 opacity-80 text-[10px] text-gray-500 dark:text-gray-400">
                                    <div class="w-1.5 h-1.5 rounded-full" style="background-color: ${node.color}"></div>
                                    <span class="uppercase font-semibold tracking-wider">${node.type}</span>
                                </div>
                                ${node.description ? `<div class="mt-1.5 pt-1.5 border-t border-gray-200 dark:border-gray-700 text-[11px] leading-snug opacity-90">${node.description}</div>` : ''}
                            </div>`}
                            nodeColor={node => node.color}
                            nodeCanvasObject={paintNode}
                            linkCanvasObject={paintLink}
                            linkPointerAreaPaint={paintLinkPointerArea}
                            linkLabel={link => `<div class="bg-white/95 dark:bg-gray-900/95 text-gray-900 dark:text-white px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 shadow-xl backdrop-blur-md font-sans text-xs max-w-xs">
                                <div class="font-bold mb-0.5">${link.keywords || link.name || 'Liên kết'}</div>
                                ${link.description ? `<div class="text-[11px] leading-snug opacity-90">${link.description}</div>` : ''}
                            </div>`}
                            linkColor={() => isDarkMode ? 'rgba(55, 65, 81, 0.4)' : 'rgba(209, 213, 219, 0.7)'}
                            linkWidth={1}
                            linkDirectionalParticles={1}
                            linkDirectionalParticleWidth={1.5}
                            linkDirectionalParticleSpeed={0.005}
                            onNodeHover={handleNodeHover}
                            onNodeClick={handleNodeClick}
                            d3AlphaDecay={0.03}
                            d3VelocityDecay={0.4}
                            cooldownTicks={200}
                        />

                        {/* Reasoning Path Banner — shown when arriving from a chat citation */}
                        {pathActive && (
                            <div className="absolute top-3 left-1/2 -translate-x-1/2 z-20 max-w-xl w-[92%]">
                                <div className="bg-white/95 dark:bg-gray-900/95 backdrop-blur-md px-4 py-3 rounded-xl border border-amber-300 dark:border-amber-700/60 shadow-lg">
                                    <div className="flex items-start gap-2.5">
                                        <div className="w-7 h-7 rounded-lg bg-amber-100 dark:bg-amber-500/10 flex items-center justify-center flex-shrink-0">
                                            <Brain className="w-4 h-4 text-amber-600 dark:text-amber-400" />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-xs font-bold text-amber-800 dark:text-amber-400">
                                                Đường đi suy luận từ câu trả lời
                                            </p>
                                            <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
                                                {pathNodes.size > 0
                                                    ? `Đã highlight ${pathNodes.size} thực thể liên quan${pathLinks.size > 0 ? ` và ${pathLinks.size} liên kết nối tiếp giữa chúng` : ''}.`
                                                    : 'Không tìm thấy thực thể nào khớp trong đồ thị hiện tại.'}
                                            </p>
                                            {pathMissing.length > 0 && (
                                                <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-1">
                                                    Không tìm thấy trong đồ thị: {pathMissing.join(', ')}
                                                </p>
                                            )}
                                        </div>
                                        <button
                                            onClick={clearPath}
                                            className="flex-shrink-0 w-6 h-6 rounded-md flex items-center justify-center text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                                            title="Đóng chế độ suy luận"
                                        >
                                            <X className="w-3.5 h-3.5" />
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Instruction Overlay */}
                        <div className="absolute top-3 left-3 z-10 pointer-events-none">
                            <div className="bg-white/80 dark:bg-gray-900/80 backdrop-blur-md px-3 py-2.5 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm pointer-events-auto">
                                <h3 className="font-bold text-gray-800 dark:text-gray-200 mb-1.5 flex items-center gap-1.5 text-[11px] uppercase tracking-wider">
                                    <BookOpen className="w-3.5 h-3.5 text-primary-500" />
                                    Hướng dẫn
                                </h3>
                                <div className="space-y-1 text-[10px] text-gray-500 dark:text-gray-400">
                                    <p className="flex items-center gap-1.5"><span>🖱️</span> Lăn chuột để Zoom</p>
                                    <p className="flex items-center gap-1.5"><span>👆</span> Click & Kéo nền để di chuyển</p>
                                    <p className="flex items-center gap-1.5"><span>🎯</span> Click vào Node để Focus</p>
                                    <p className="flex items-center gap-1.5"><span>✨</span> Hover vào Node để xem chi tiết</p>
                                </div>
                            </div>
                        </div>

                        {/* Controls Overlay */}
                        <div className="absolute top-3 right-3 flex flex-col gap-1.5 z-10">
                            <button onClick={() => fgRef.current?.zoom(fgRef.current.zoom() * 1.2, 400)} className="w-8 h-8 rounded-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 flex items-center justify-center text-gray-500 hover:text-gray-900 dark:hover:text-white hover:border-gray-300 dark:hover:border-gray-700 transition-colors shadow-sm focus:outline-none">
                                <ZoomIn className="w-4 h-4" />
                            </button>
                            <button onClick={() => fgRef.current?.zoom(fgRef.current.zoom() / 1.2, 400)} className="w-8 h-8 rounded-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 flex items-center justify-center text-gray-500 hover:text-gray-900 dark:hover:text-white hover:border-gray-300 dark:hover:border-gray-700 transition-colors shadow-sm focus:outline-none">
                                <ZoomOut className="w-4 h-4" />
                            </button>
                            <button onClick={() => fgRef.current?.zoomToFit(400, 50)} className="w-8 h-8 rounded-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 flex items-center justify-center text-gray-500 hover:text-gray-900 dark:hover:text-white hover:border-gray-300 dark:hover:border-gray-700 transition-colors shadow-sm mt-1 focus:outline-none" title="Vừa toàn bộ màn hình">
                                <Maximize2 className="w-4 h-4" />
                            </button>
                        </div>

                        {/* Interactive Legend (Bottom Left) */}
                        <div className="absolute bottom-4 left-4 flex flex-wrap gap-2 z-10 max-w-2xl pointer-events-none">
                            {stats.legendItems.slice(0, 8).map(item => (
                                <div key={item.type} className="flex items-center gap-1.5 bg-white/90 dark:bg-gray-900/90 backdrop-blur-sm px-2.5 py-1 rounded-md border border-gray-200 dark:border-gray-800 pointer-events-auto shadow-sm">
                                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: item.color }} />
                                    <span className="text-[10px] font-bold uppercase tracking-wider text-gray-600 dark:text-gray-400">{item.type}</span>
                                </div>
                            ))}
                        </div>
                    </>
                )}
            </div>

            {/* Bottom Panels (Stats & Top Entities) - Only show if data exists */}
            {!loading && graphData.nodes.length > 0 && (
                <div className="h-52 shrink-0 flex gap-2 lg:gap-3 z-10">

                    {/* Type Distribution Panel */}
                    <div className="flex-1 min-w-[300px] border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-950 rounded-xl p-4 flex flex-col shadow-sm">
                        <div className="flex items-center justify-between mb-3 border-b border-gray-200 dark:border-gray-800 pb-2">
                            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-700 dark:text-gray-300 flex items-center gap-1.5">
                                <Hash className="w-3.5 h-3.5 text-primary-500" />
                                Thành phần Đồ thị
                            </h3>
                            <span className="text-[10px] font-bold text-gray-500 dark:text-gray-500 uppercase tracking-wider">{stats.totalNodes} Thực thể · {stats.totalLinks} Liên kết</span>
                        </div>

                        <div className="flex-1 overflow-y-auto custom-scrollbar flex flex-wrap gap-2 content-start pr-1">
                             {stats.legendItems.map(item => (
                                 <div key={item.type} className="flex items-center gap-2 w-[calc(50%-0.5rem)] mb-1 bg-white dark:bg-gray-900 px-2 py-1.5 rounded-lg border border-gray-100 dark:border-gray-800">
                                     <div className="w-2 h-2 rounded-full shadow-inner" style={{ backgroundColor: item.color }} />
                                     <span className="textxs font-medium text-gray-600 dark:text-gray-400 capitalize truncate flex-1" title={item.type}>{item.type}</span>
                                     <span className="text-xs font-bold text-gray-900 dark:text-gray-200 bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-center">{item.count}</span>
                                 </div>
                             ))}
                        </div>
                    </div>

                    {/* Top Entities Panel */}
                    <div className="flex-1 min-w-[300px] border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-950 rounded-xl p-4 flex flex-col shadow-sm">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-gray-700 dark:text-gray-300 flex items-center gap-1.5 mb-3 border-b border-gray-200 dark:border-gray-800 pb-2">
                            <LinkIcon className="w-3.5 h-3.5 text-emerald-500" />
                            Thực thể Trọng tâm
                        </h3>

                        <div className="flex-1 overflow-y-auto custom-scrollbar space-y-1.5 pr-2">
                            {stats.topEntities.map((entity, i) => (
                                <div key={entity.id} className="flex items-center justify-between group bg-white dark:bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-100 dark:border-gray-800 hover:border-gray-300 dark:hover:border-gray-700 transition-colors">
                                    <div className="flex items-center gap-2.5 overflow-hidden">
                                        <span className="text-[10px] font-black text-gray-400 dark:text-gray-600 w-3">{i + 1}</span>
                                        <span className="text-xs text-gray-800 dark:text-gray-200 font-medium truncate group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors cursor-default" title={entity.name}>
                                            {entity.name}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                                        <span className="text-[10px] uppercase tracking-wider font-semibold text-gray-500">{entity.type}</span>
                                        <span className="text-xs font-mono bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 px-1.5 py-0.5 rounded font-bold w-6 text-center">{entity.rawDegree}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                </div>
            )}
        </div>
    );
}
