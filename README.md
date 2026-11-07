# Lesson Studio

A small, local lesson-research dashboard with a responsive layout, more readable type, and a locally served 3D-style SVG hero illustration. It accepts a lesson title and learning objective, discovers web references and research links for books and videos, adds licensed Wikimedia Commons photos with attribution to the lesson, runs two separate heuristic QC checks, and supports editing, browser-local saving, preview, applying recommendations, and Markdown export with both QC reports. Run QC again after edits; export reruns both checks so its reports match the final draft.

## Project files

- `server.py` — local web server, research retrieval, lesson generation, and QC endpoints.
- `index.html`, `styles.css`, `app.js` — responsive dashboard and lesson workflow.
- `dashboard-illustration.svg` — locally served dashboard illustration.
- `test_server.py` — automated workflow and API tests.

## Run locally

Requires Python 3.9+; no packages are required. The local generator works without API keys. To use OpenAI for lesson drafting, set `OPENAI_API_KEY` before starting the server; optionally set `OPENAI_MODEL` (defaults to `gpt-4o-mini`). Hosted generation sends the lesson prompt and retrieved research notes to that provider. Set `YOUTUBE_API_KEY` to retrieve specific video results and descriptions; without it, the app provides a topic-specific YouTube search link and clearly flags that no video was reviewed.

```powershell
python server.py
```

Open [http://localhost:8000](http://localhost:8000). Use **Try a sample** for the requested HTTP example, then generate, inspect both QC panels, edit the draft, preview, and export. The dashboard sidebar links to the lesson setup, research, and quality review sections. Try a second lesson, for example:

- Title: **Photosynthesis: From Light to Chemical Energy**
- Objective: **Describe how plants use light, water, and carbon dioxide to produce sugars and oxygen.**

Research retrieval queries Wikipedia and the Google Books catalog (with an Open Library fallback) for relevant pages/snippets and titles. HTTP lessons include the HTTP Semantics specification and relevant MDN references. Internet access is needed for live search. Source discovery errors and unavailability of the optional YouTube API key are surfaced in the research panel; the rest of the workflow remains usable.

## Design and limitations

- The no-credential default uses a deterministic, source-linked local lesson generator so the workflow works offline and is repeatable. It is not a hosted LLM. QC reports are transparent heuristic checks, not proof of factual accuracy or a replacement for instructor review.
- When `OPENAI_API_KEY` is configured, lesson drafting uses the OpenAI Chat Completions API; research retrieval and both independent QC checks remain in this app. Provider errors are surfaced and do not replace the saved draft.
- Research links and snippets are starting points. Verify claims against original/primary sources and preview a specific video before assigning it.
- Browser `localStorage` preserves the draft and QC reports on the current browser/device. Export a Markdown file to share or back it up.
- **Create new lesson** saves the current work in the dashboard's Saved lessons list, then opens a blank draft. Select a saved lesson in that list to return to it.
- Failed requests surface errors and leave the existing draft intact; research and generation can be retried.

## Demo walkthrough

1. Load **HTTP Requests and Responses**, run research and generation, and open the RFC/MDN sources.
2. Show the separate research-accuracy and instructional-quality reports.
3. Edit the lesson, run both QC checks, preview it, and export the lesson and refreshed QC reports.
4. Repeat with the photosynthesis example above; verify the textbook and topic references and note any reported research-source limitations.

## Verify

Run the focused checks:

```powershell
python -m unittest -v
```
