# Publish the Hong Kong Air Quality Briefing System

## Preview locally

From the project root with Python 3.10 or later, run:

```powershell
python -m pip install -r requirements_task_d.txt
python -m src.site_export
python -m pytest -v tests/test_task_d.py
python -m http.server 8000 --bind 127.0.0.1 --directory docs
```

Open [the local preview](http://127.0.0.1:8000/). Check both example dates, the General
and Roadside map layers, and the HTML and Markdown versions of the briefings.
Leaflet and the OpenStreetMap basemap require browser network access.

The homepage lists selected pre-generated examples. In `task_d_demo.ipynb`,
pick any 2025 date and click **Show District Map** for the interactive map.
To replace the published examples with selected dates, use the `demo_cases`
example in [the export guide](docs/README_EXPORT.md).

## Hand off to the group leader

Copy `src/viz.py`, `src/task_d_integration.py`, `src/site_export.py`,
`task_d_demo.ipynb`, `requirements_task_d.txt`, `tests/test_task_d.py`, the
verification and publishing guides, and `docs/` into the team's existing project.
Keep `src/` and `data/` at the project root alongside the notebook.
The group leader can run the Task D notebook as a standalone demo or adopt its
setup, report, charts, map and export cells in `main.ipynb`. Run the export and
tests again if the team updates the SQL or templates. Existing valid report
history takes precedence over the sample briefings when rebuilding the site.

## Enable Pages in the team's repository

1. Use the existing repository and approved publishing branch. Commit the verified
   `docs/` tree, including `docs/.nojekyll`. Check that `docs/` contains only
   the intended publication files.
2. In GitHub, go to **Settings → Pages**. Under **Build and deployment**, select
   **Deploy from a branch**, pick the approved branch and choose **/docs**. Save.
3. Check the Pages workflow result and open the address shown under Pages settings.
   Repeat the date, report and map checks on the live site.

For the GitHub UI and permission requirements, see the
[official GitHub Pages publishing guide](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).
