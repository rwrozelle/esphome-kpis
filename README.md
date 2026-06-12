# ESPHome Component KPIs

An automated dashboard that tracks health metrics for every component in the
[ESPHome](https://github.com/esphome/esphome) repository.

**[View the live table →](https://rwrozelle.github.io/esphome-kpis/)**

Updated nightly by GitHub Actions.

## What it tracks

| Column | Description |
|---|---|
| Component | Directory name under `esphome/components/` |
| Type | Entity type (sensor, switch, climate, …) derived from code structure and docs |
| Created | ESPHome release version when the component first appeared |
| Last Modified | Most recent ESPHome release that touched the component |
| Last Commit | ISO date of the most recent git commit |
| Platforms | Hardware platforms the component is restricted to (`any` = no restriction detected) |
| #Tests | Number of YAML test files under `tests/components/<name>/` |
| Codeowners | GitHub handles from the repository `CODEOWNERS` file |
| Issues | Open GitHub issues attributed to this component |
| PRs | Open GitHub pull requests attributed to this component |

## Running locally

```bash
pip install -e .

# Collect (needs a local esphome clone or omit --esphome-root to auto-clone)
esphome-kpis --esphome-root /path/to/esphome --output data/components.json

# Render HTML
esphome-kpis-render data/components.json -o data/index.html
```

Set `GITHUB_TOKEN` in your environment to avoid GitHub API rate limits.

## Data sources

- [github.com/esphome/esphome](https://github.com/esphome/esphome) — component structure, git history, CODEOWNERS, test files
- [github.com/esphome/esphome.io](https://github.com/esphome/esphome.io) — component category information
- [GitHub Issues API](https://github.com/esphome/esphome/issues) — open issues and pull requests
