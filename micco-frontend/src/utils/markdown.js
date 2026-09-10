/**
 * markdown.js — the markdown renderer shared by the internal chat and the
 * business portal.
 *
 * Output is fed to `dangerouslySetInnerHTML`, so the source text is escaped
 * before any transformation runs. Order matters:
 *
 *   1. extract math into placeholders — KaTeX must see the raw formula, so
 *      this happens before escaping (`x < y` would otherwise reach it as
 *      `x &lt; y`),
 *   2. escape everything that is left, so model output and document text can
 *      never introduce markup,
 *   3. transform markdown into our own trusted HTML,
 *   4. restore the math placeholders.
 *
 * Extracted from ChatAssistant.jsx, where it ran unescaped.
 */

const HTML_ESCAPES = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
};

/** Escape text for interpolation into markup or an attribute value. */
export function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value).replace(/[&<>"']/g, (char) => HTML_ESCAPES[char]);
}

function extractMath(text, mathBlocks) {
    const hasKatex = typeof window !== 'undefined' && window.katex;
    let html = text;

    // Block math: $$ ... $$
    html = html.replace(/\$\$([\s\S]+?)\$\$/g, (match, formula) => {
        if (!hasKatex) return match;
        try {
            const rendered = window.katex.renderToString(formula.trim(), { displayMode: true, throwOnError: false });
            const id = `__MATH_BLOCK_${mathBlocks.length}__`;
            mathBlocks.push({ id, html: `<div class="katex-display-wrapper my-4 overflow-x-auto">${rendered}</div>` });
            return id;
        } catch { return match; }
    });

    // Inline math: $ ... $
    html = html.replace(/\$([^\s$][^$]*?[^\s$])\$/g, (match, formula) => {
        if (!hasKatex) return match;
        try {
            const rendered = window.katex.renderToString(formula, { displayMode: false, throwOnError: false });
            const id = `__MATH_INLINE_${mathBlocks.length}__`;
            mathBlocks.push({ id, html: `<span class="katex-inline">${rendered}</span>` });
            return id;
        } catch { return match; }
    });

    return html;
}

function renderTables(html) {
    const lines = html.split('\n');
    let inTable = false;
    let tableHtml = '';
    const processedLines = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        // A line that looks like a table row: has a pipe and isn't a separator
        if (line.includes('|')) {
            if (!inTable) {
                inTable = true;
                tableHtml = '<div class="table-container my-3 overflow-x-auto border border-gray-100 dark:border-gray-800 rounded-lg shadow-sm"><table class="min-w-full text-xs text-left text-gray-700 dark:text-gray-300 border-collapse">';
            }

            // Drop the empty first/last cells produced by leading/trailing pipes
            const cells = line.split('|').map((c) => c.trim());
            if (cells[0] === '') cells.shift();
            if (cells[cells.length - 1] === '') cells.pop();

            if (line.includes('---') || line.match(/^[|\s:-]+$/)) {
                continue;
            }

            const isHeader = !tableHtml.includes('<tbody>');
            if (isHeader && !tableHtml.includes('<thead>')) {
                tableHtml += '<thead><tr class="bg-gray-50/80 dark:bg-gray-800/50 border-b border-gray-100 dark:border-gray-800">';
                cells.forEach((c) => { tableHtml += `<th class="px-4 py-2 font-bold text-gray-900 dark:text-white">${c}</th>`; });
                tableHtml += '</tr></thead><tbody>';
            } else {
                tableHtml += '<tr class="border-b border-gray-50 dark:border-gray-800/50 last:border-0 hover:bg-gray-50/50 dark:hover:bg-gray-800/30 transition-colors">';
                cells.forEach((c) => { tableHtml += `<td class="px-4 py-2">${c}</td>`; });
                tableHtml += '</tr>';
            }
        } else {
            if (inTable) {
                tableHtml += '</tbody></table></div>';
                processedLines.push(tableHtml);
                inTable = false;
                tableHtml = '';
            }
            processedLines.push(lines[i]);
        }
    }
    if (inTable) {
        tableHtml += '</tbody></table></div>';
        processedLines.push(tableHtml);
    }

    return processedLines.join('\n');
}

function renderInlineAndBlocks(html) {
    return html
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`([^`]+)`/g, '<code class="px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-[10px] font-mono text-pink-600 dark:text-pink-400">$1</code>')
        .replace(/```([\s\S]*?)```/g, '<pre class="my-2 p-3 rounded-xl bg-gray-100 dark:bg-gray-800 text-[10px] font-mono overflow-x-auto border border-gray-200 dark:border-gray-700"><code>$1</code></pre>')
        .replace(/^#{3}\s+(.+)$/gm, (match, p1) => `<h3 id="h3-${p1}" class="font-black text-xs mt-3 mb-1 text-gray-900 dark:text-white uppercase tracking-wider">${p1}</h3>`)
        .replace(/^#{2}\s+(.+)$/gm, (match, p1) => `<h2 id="h2-${p1}" class="font-black text-sm mt-4 mb-1.5 text-gray-900 dark:text-white uppercase tracking-wider">${p1}</h2>`)
        .replace(/^#{1}\s+(.+)$/gm, (match, p1) => `<h1 id="h1-${p1}" class="font-black text-base mt-5 mb-2 text-gray-900 dark:text-white uppercase tracking-wider">${p1}</h1>`)
        .replace(/^[-*]\s+(.+)$/gm, '<li class="ml-4 list-disc text-gray-700 dark:text-gray-300">$1</li>')
        .replace(/(<li.*<\/li>)/gs, '<ul class="my-1.5 space-y-0.5">$1</ul>');
}

function renderParagraphs(html) {
    return html
        .split(/\n\n+/)
        .map((p) => {
            if (p.startsWith('<') && (p.includes('<h') || p.includes('<pre') || p.includes('<ul') || p.includes('<div') || p.includes('<table'))) {
                return p;
            }
            return `<p class="mb-1 last:mb-0">${p.replace(/\n/g, '<br/>')}</p>`;
        })
        .join('\n');
}

function renderCitations(html, sources) {
    if (!sources || sources.length === 0) return html;

    return html.replace(/\[([a-zA-Z0-9_\-.:?]+)\]/g, (match, marker) => {
        const src = sources.find(
            (s) => s.index === marker
                || s.formatted === marker
                || s.source_file === marker
                || `doc:${s.document_id}` === marker,
        );
        if (!src) return match;

        const title = escapeHtml(`Nguồn: ${src.source_file || src.formatted || src.document_id}`);
        return `<button type="button" class="citation inline-flex items-center justify-center px-1.5 py-0.5 mx-0.5 text-[10px] font-bold rounded bg-emerald-100/80 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400 hover:bg-emerald-200 dark:hover:bg-emerald-500/40 transition-colors cursor-pointer align-baseline ring-1 ring-emerald-200 dark:ring-emerald-500/30" data-source-id="${escapeHtml(src.document_id)}" data-index="${escapeHtml(src.index || '')}" title="${title}">[${escapeHtml(marker)}]</button>`;
    });
}

/**
 * Render markdown to HTML for `dangerouslySetInnerHTML`.
 *
 * @param {string} text Raw markdown, treated as untrusted.
 * @param {Array} sources Optional citation sources, used to turn `[doc:1]`
 *   markers into clickable chips.
 */
export function renderMarkdown(text, sources = []) {
    if (!text) return '';

    const mathBlocks = [];
    let html = extractMath(text, mathBlocks);

    // Everything after this point generates markup, so nothing that came from
    // the model or a document may still be raw.
    html = escapeHtml(html);

    html = renderTables(html);
    html = renderInlineAndBlocks(html);
    html = renderParagraphs(html);
    html = renderCitations(html, sources);

    mathBlocks.forEach((block) => {
        html = html.replace(block.id, block.html);
    });

    return `<div class="markdown-content">${html}</div>`;
}
