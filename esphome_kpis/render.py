"""Render ESPHome component KPI JSON to a self-contained HTML table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote

_GH_ISSUES = "https://github.com/esphome/esphome/issues?q={q}"


def _gh_link(name: str, kind: str, count: int | str) -> str:
    """Wrap count in a GitHub search link using component name as text search."""
    if not count:
        return ""
    q = quote(f'is:{kind} is:open {name}')
    return f'<a href="{_GH_ISSUES.format(q=q)}" target="_blank" rel="noopener">{count}</a>'


def _row(name: str, data: dict) -> str:
    types = ", ".join(data.get("type", [name]))
    platforms = " ".join(data.get("supported_platforms", [])) or "any"
    owners_list = data.get("codeowners", [])
    owners_display = " ".join(owners_list) or "N/A"

    test_count = data.get("test_file_count", 0) or ""
    issues = _gh_link(name, "issue", data.get("open_issues") or "")
    prs = _gh_link(name, "pr", data.get("open_prs") or "")

    return (
        f'<tr data-name="{name}" data-type="{types}" '
        f'data-platforms="{platforms}" data-owners="{owners_display}">\n'
        f'  <td>{name}</td>\n'
        f'  <td>{types}</td>\n'
        f'  <td>{data.get("version_created") or ""}</td>\n'
        f'  <td>{data.get("version_last_modified") or ""}</td>\n'
        f'  <td>{data.get("last_commit_date") or ""}</td>\n'
        f'  <td>{platforms}</td>\n'
        f'  <td style="text-align:right">{test_count}</td>\n'
        f'  <td style="font-size:0.85em">{owners_display}</td>\n'
        f'  <td style="text-align:right">{issues}</td>\n'
        f'  <td style="text-align:right">{prs}</td>\n'
        f'</tr>'
    )


_FOOTER = """\
<div class="footer">
  <p class="unattr">
    <strong>Attribution coverage:</strong>
    Of {total_issues} open issues: {known_issues} are shown in this table,
    and {unattr_issues} could not be matched to any component.<br>
    Of {total_prs} open PRs: {known_prs} are shown in this table,
    {new_comp_prs} are for new components not yet in the repo (expected — new-component PRs
    carry a label for a component name that doesn't exist yet),
    and {unattr_prs} could not be matched to any component.
  </p>

  <details>
    <summary>How each column is generated</summary>
    <dl>
      <dt>Component</dt>
      <dd>Directory name under <code>esphome/components/</code> in the ESPHome repository,
          filtered to files tracked by git (excludes local WIP directories).</dd>

      <dt>Type</dt>
      <dd>Derived in priority order: (1)&nbsp;self-identification — the component is itself a
          known entity type (sensor, switch…); (2)&nbsp;curated taxonomy for infrastructure
          components (buses, platforms, networking); (3)&nbsp;esphome.io docs tree — the
          category subdirectory the component is documented under; (4)&nbsp;file/directory
          scan — subdirectories or <code>.py</code> files named after entity types;
          (5)&nbsp;import scan of <code>__init__.py</code>; (6)&nbsp;fallback to component
          name when nothing else matches.</dd>

      <dt>Created / Last Modified</dt>
      <dd>ESPHome release version mapped from the first and most recent git commit dates
          touching <code>esphome/components/&lt;name&gt;/</code>.</dd>

      <dt>Last Commit</dt>
      <dd>ISO date of the most recent git commit to the component directory.</dd>

      <dt>Platforms</dt>
      <dd>Hardware platforms the component is restricted to, derived from
          <code>cv.only_on_*</code> / <code>cv.only_on([…])</code> validators and
          <code>DEPENDENCIES</code> lists in <code>__init__.py</code>, combined with
          <code>#ifdef USE_&lt;PLATFORM&gt;</code> guards in the first five lines of
          <code>.h</code> / <code>.cpp</code> files.
          <em>any</em> means no restriction was detected — the component likely runs
          on all platforms, but detection is heuristic.</dd>

      <dt>#Tests</dt>
      <dd>Number of YAML test files found under
          <code>tests/components/&lt;name&gt;/</code>.</dd>

      <dt>Codeowners</dt>
      <dd>GitHub handles listed for this component in the repository
          <code>CODEOWNERS</code> file. <em>N/A</em> means the component has no
          declared owner.</dd>

      <dt>Issues / PRs</dt>
      <dd>Count of currently open GitHub issues and pull requests attributed to this
          component. Attribution uses (in order): <code>component:&nbsp;&lt;name&gt;</code>
          labels, <code>[component_name]</code> bracket notation in the title,
          underscore-containing component names found anywhere in the title, and
          short component names found at the very start of the title.
          The count is a clickable link to a broad GitHub text search for the component
          name — the search result may show more or fewer items than the count.</dd>
    </dl>
  </details>

  <details>
    <summary>Data sources</summary>
    <ul>
      <li><a href="https://github.com/esphome/esphome">github.com/esphome/esphome</a> —
          component structure, git history, CODEOWNERS, test files</li>
      <li><a href="https://github.com/esphome/esphome.io">github.com/esphome/esphome.io</a> —
          component category information (docs tree)</li>
      <li><a href="https://github.com/esphome/esphome/issues">GitHub Issues API</a> —
          open issues and pull requests</li>
    </ul>
    <p>Generated by
      <a href="https://github.com/rwrozelle/esphome-kpis">rwrozelle/esphome-kpis</a>.
    </p>
  </details>
</div>
"""

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ESPHome Component KPIs</title>
<style>
  body {{ font-family: sans-serif; font-size: 13px; padding: 16px; }}
  h1 {{ font-size: 1.4em; margin-bottom: 6px; }}
  .meta {{ color: #666; margin-bottom: 12px; }}
  .filters {{ display: flex; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }}
  .filters input {{
    padding: 6px 10px; font-size: 13px;
    border: 1px solid #ccc; border-radius: 4px;
  }}
  #filter       {{ width: 260px; }}
  #plat-filter  {{ width: 180px; }}
  #owner-filter {{ width: 180px; }}
  .filter-count {{ line-height: 30px; color: #666; font-size: 12px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th {{
    background: #f0f0f0; cursor: pointer; padding: 6px 8px;
    text-align: left; border: 1px solid #ddd; white-space: nowrap;
  }}
  th:hover {{ background: #e0e0e0; }}
  th.sort-asc::after  {{ content: " ▲"; }}
  th.sort-desc::after {{ content: " ▼"; }}
  td {{ padding: 4px 8px; border: 1px solid #eee; vertical-align: top; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  tr:hover {{ background: #f5f8ff; }}
  tr.hidden {{ display: none; }}
  .footer {{ margin-top: 28px; border-top: 1px solid #ddd; padding-top: 16px; color: #444; }}
  .footer p, .footer li {{ margin: 4px 0; line-height: 1.5; }}
  .unattr {{ margin-bottom: 14px; }}
  .footer details {{ margin-bottom: 10px; }}
  .footer summary {{ cursor: pointer; font-weight: bold; color: #333; margin-bottom: 6px; }}
  .footer dl {{ margin: 8px 0 0 16px; }}
  .footer dt {{ font-weight: bold; margin-top: 8px; }}
  .footer dd {{ margin: 2px 0 0 20px; }}
  .footer ul {{ margin: 6px 0 0 20px; padding: 0; }}
  .footer a {{ color: #0969da; }}
</style>
</head>
<body>
<h1>ESPHome Component KPIs</h1>
<p class="meta">{n_components} components &nbsp;·&nbsp; generated {date}</p>
<div class="filters">
  <input id="filter"       type="text" placeholder="Component name or type…">
  <input id="plat-filter"  type="text" placeholder="Platform (e.g. esp32)…">
  <input id="owner-filter" type="text" placeholder="Codeowner (e.g. @user)…">
  <span class="filter-count" id="row-count"></span>
</div>
<table id="kpi-table">
<thead><tr>
  <th>Component</th>
  <th>Type</th>
  <th>Created</th>
  <th>Last Modified</th>
  <th>Last Commit</th>
  <th>Platforms</th>
  <th>#Tests</th>
  <th>Codeowners</th>
  <th>Issues</th>
  <th>PRs</th>
</tr></thead>
<tbody>
{rows}
</tbody>
</table>
{footer}
<script>
(function() {{
  const tbody = document.querySelector('#kpi-table tbody');
  const rows  = Array.from(tbody.querySelectorAll('tr'));
  const countEl = document.getElementById('row-count');

  function applyFilters() {{
    const name  = document.getElementById('filter').value.toLowerCase();
    const plat  = document.getElementById('plat-filter').value.toLowerCase().trim();
    const owner = document.getElementById('owner-filter').value.toLowerCase().trim();
    let visible = 0;
    for (const row of rows) {{
      const rName  = row.dataset.name;
      const rType  = row.dataset.type;
      const rPlats = row.dataset.platforms;   // space-separated, blank = unrestricted
      const rOwners = row.dataset.owners.toLowerCase();

      const nameOk  = !name  || rName.includes(name)  || rType.includes(name);
      const platOk  = !plat  || rPlats.includes(plat);
      const ownerOk = !owner || rOwners.includes(owner);

      const show = nameOk && platOk && ownerOk;
      row.classList.toggle('hidden', !show);
      if (show) visible++;
    }}
    countEl.textContent = visible + ' shown';
  }}

  document.getElementById('filter').addEventListener('input', applyFilters);
  document.getElementById('plat-filter').addEventListener('input', applyFilters);
  document.getElementById('owner-filter').addEventListener('input', applyFilters);

  // Column sort
  const ths = document.querySelectorAll('#kpi-table th');
  let sortCol = -1, sortAsc = true;
  ths.forEach((th, i) => {{
    th.addEventListener('click', () => {{
      sortAsc = (sortCol === i) ? !sortAsc : true;
      sortCol = i;
      ths.forEach(t => t.classList.remove('sort-asc', 'sort-desc'));
      th.classList.add(sortAsc ? 'sort-asc' : 'sort-desc');
      const sorted = rows.slice().sort((a, b) => {{
        const av = a.cells[i]?.textContent.trim() || '';
        const bv = b.cells[i]?.textContent.trim() || '';
        const n = parseFloat(av), m = parseFloat(bv);
        const cmp = (!isNaN(n) && !isNaN(m)) ? (n - m) : av.localeCompare(bv);
        return sortAsc ? cmp : -cmp;
      }});
      sorted.forEach(r => tbody.appendChild(r));
    }});
  }});

  applyFilters();
}})();
</script>
</body>
</html>
"""


def render(data: dict, output_path: Path) -> None:
    components = data.get("components", {})
    generated_at = data.get("generated_at", "")[:10]
    rows_html = "\n".join(_row(name, comp) for name, comp in sorted(components.items()))

    stats = data.get("issue_stats", {})
    footer = _FOOTER.format(
        total_issues  = stats.get("total_issues", 0),
        known_issues  = stats.get("known_issues", 0),
        unattr_issues = stats.get("unattr_issues", 0),
        total_prs     = stats.get("total_prs", 0),
        known_prs     = stats.get("known_prs", 0),
        new_comp_prs  = stats.get("new_comp_prs", 0),
        unattr_prs    = stats.get("unattr_prs", 0),
    )

    html = _HTML_TEMPLATE.format(
        n_components=len(components),
        date=generated_at,
        rows=rows_html,
        footer=footer,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render ESPHome KPI JSON to HTML")
    parser.add_argument("input", type=Path, help="components.json produced by esphome-kpis")
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Output HTML path (default: same dir as input, .html extension)",
    )
    args = parser.parse_args()

    data = json.loads(args.input.read_text())
    output = args.output or args.input.with_suffix(".html")
    render(data, output)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
