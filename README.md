# Curiosity Dispatch: Kris's automated newspaper

Built from Nur's **Neat** starter kit. The collector, checker, and static-site builder
remain plain Python. The replacement curator calls **Gemini 2.5 Flash-Lite** through
Google's Gemini API, selects from the already-sanitized candidate pool, and never
browses the web or has repository access itself.

**Status:** Customized starter, smoke-tested locally. Needs your GitHub repository,
GitHub Pages setup, and a free-tier Gemini key before its first live run.

## What you can customize

| File | What it controls |
| --- | --- |
| `profile.md` | Your interests, priorities, avoid-list, and editorial voice. This is a draft; edit it. |
| `collector/sources.txt` | The RSS feeds and what topic each belongs to. Add/remove lines whenever you like. |
| `check_picks.py` (`CATEGORIES`) | Allowed category names; keep these consistent with `sources.txt`. |
| `site_config.py` | Working name `Curiosity Dispatch`, tagline and optional site URL. |
| `fortunes.txt` | Random footer lines. |
| `icons/` | Optional section SVG icons; filenames match category slugs. |
| `collector/collect.py` (`BLOCK_RUST`) | Off by default; no inherited censorship of Rust. |

## One-time GitHub setup (no paid API necessary)

1. **Create a PUBLIC GitHub repository** (for example, `curiosity-dispatch`) on your
   account. Do not publish your Gemini API key or personal/private content in the repo.
   A public repo makes GitHub Pages and standard GitHub-hosted Actions free under
   GitHub's current rules. For a private repo, use a supported alternate host such
   as Cloudflare Pages; Github Pages availability varies by plan.
2. **Upload the CONTENTS** of this ZIP's `neat-starter/` directory to the repository
   root, including `.github/workflows/`. The default branch must be named `main`.
3. In the GitHub repository, go to **Settings → Actions → General → Workflow
   permissions**, and permit GitHub Actions to create commits (`Read and write permissions`),
   if the setting is configurable. If repo/org policies override this, adjust them.
4. Get a key from [Google AI Studio](https://aistudio.google.com/apikey).
   **Use a project on the Gemini Free Tier, with NO billing account linked.**
   This is the critical protection against an unexpected bill. Gemini's free-tier
   limits vary; confirm the project and selected model still qualify in AI Studio.
5. Go to **Settings → Secrets and variables → Actions → New repository secret**:
   name `GEMINI_API_KEY`, paste the key as its value. Never put it into a file.
6. Under **Settings → Pages**, set **Build and deployment → Source** to
   **GitHub Actions**. If you use a custom domain later, set the optional repository
   variable `SITE_URL` to its full `https://.../` address.
7. Go to the **Actions** tab. Enable workflows if GitHub asks, then run
   **Collect feeds → Run workflow**. Inspect `candidates.json` for useful stories,
   and review the `sources` diagnostics for broken feeds.
8. Run **Curate news with Gemini (free tier) → Run workflow**. The script should add
   up to eight stories, validate them with `check_picks.py`, build the site and push.
   Its `publish` job deploys GitHub Pages. You can also run **Publish newspaper to
   GitHub Pages** by itself.
9. Your first URL will normally be
   `https://YOUR-GITHUB-USERNAME.github.io/YOUR-REPOSITORY-NAME/`.
   The RSS feed is at the same URL plus `feed.xml`.

### Automatic schedule

- Feed collection: every 4 hours (UTC GitHub Actions cron).
- AI editing: approx. **06:43, 12:43, and 17:43 America/Chicago** each day.
  The scheduled workflow checks local time so DST doesn't move publishing by an hour.
  GitHub schedule delivery can be delayed or occasionally skipped.
- Publication: immediately after a successful curation, without keeping your
  computer running.

## Free-tier limits and privacy

- Gemini model is pinned to `gemini-2.5-flash-lite` in `curator/curate.py`.
  No paid-model fallback or tool/browser use is implemented.
- **Free-tier does NOT mean any account key is automatically free.** If you enable
  Google Cloud billing for that project, usage may be charged. Use an unbilled,
  free-tier-eligible project and check its actual quotas in AI Studio.
- Gemini returns HTTP 429 when quotas are exhausted. The curator fails without
  touching `items.json` or `seen.txt`; the existing newspaper remains live.
- Google may use free-tier prompts/responses to improve products. The curator
  sends only public article titles/summaries plus your editorial profile and
  recent story titles. Do not put secrets or sensitive personal info in the profile.
- All submitted articles should be treated as untrusted. The existing collector
  attempts prompt-injection sanitization, the model has no browsing/tools, the
  script only accepts candidate **indexes** and reconstructs trusted links, and the
  independent checker validates the final articles before commit.
- **GitHub Pages deployment is separate from GitHub's push-trigger security.** A
  commit made by GitHub Actions' built-in `GITHUB_TOKEN` does not normally trigger
  a new `push` workflow. The curator explicitly calls the reusable publish workflow.

## Local tests (without internet or API key)

```bash
python3 -I collector/test_sanitise.py
python3 -I curator/test_curate.py
python3 -I curator/curate.py --dry-run
python3 -I check_picks.py
python3 -I build_feed.py
```

The starter's `candidates.json` is empty until the collector runs, so a dry run
initially shows zero candidates. Live feed collection/API inference requires
GitHub Actions or a machine with internet access and the correct secret.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| `Missing GEMINI_API_KEY` | Add the repository secret exactly as written. |
| `HTTP 429` | Free quota exhausted; wait until quota resets or reduce schedule/pool size. No paid fallback occurs. |
| `HTTP 403` | Check key validity, service/project access and model eligibility. |
| `No unused candidates` | Run the collector; inspect `candidates.json` source diagnostics. |
| `Resource not accessible by integration` on push | Enable Actions write permissions; check branch protection. |
| GitHub Pages deploy fails | Enable Pages with GitHub Actions source in Settings → Pages; check Pages permissions. |
| Build works but site empty | Run collector and curator in that order; verify valid article summaries exist. |
| Model makes up facts | Tighten `profile.md` and `RUN.md`, or decrease candidate summary truncation. Never bypass checker. |

### Note on Nur's original code

This is a modification of the files Nur supplied, not a ground-up rewrite.
The original `collector/collect.py`, `check_picks.py`, `build_feed.py`, and
`build_site.py` are preserved and adapted to the new categories, branding,
America/Chicago time and a Gemini curator.
