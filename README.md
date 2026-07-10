# Composio App Research & AI Buildability Pipeline

An autonomous research pipeline built to evaluate developer API readiness, auth barriers, and AI agent compatibility across 100 industry-standard SaaS integrations.

## What the Pipeline Does
The pipeline leverages the Composio SDK paired with web-searching toolsets (via Tavily API) and Google's Gemini 1.5 Flash LLM. It systematically scrapes and processes developer documentation to output verified JSON data (`results_verified.json`). The process includes a two-pass validation loop: a separate verification agent checks a stratified sample of the results, flags any data discrepancies for human review, calculates accuracy rates, and automatically generates a stunning, premium HTML findings matrix at `site/index.html`.

---

## Getting Started

### 1. Install Dependencies
Make sure you have Python 3.8+ installed. Install the required Python packages:
```bash
pip install -r requirements.txt
```

### 2. Set Up Environment Variables
Copy the `.env.example` file to `.env`:
```bash
cp .env.example .env
```
Open `.env` and fill in your API credentials:
* **`COMPOSIO_API_KEY`**: Get a free API key at [composio.dev](https://app.composio.dev/).
* **`GEMINI_API_KEY`**: Obtain a free-tier API key at [Google AI Studio](https://aistudio.google.com/app/apikey).
* **`TAVILY_API_KEY`**: Sign up for a free search tier (1,000 monthly searches) at [tavily.com](https://tavily.com/).

### 3. Run the Pipeline End-to-End
Execute all stages sequentially (runs unit tests, pass-1 research, pass-2 verification, pattern extraction, and HTML report generation):
```bash
python run_pipeline.py --stage all
```

---

## Stage-by-Stage Executions
You can also run specific stages of the pipeline:

* **Run Test Suite**: Validate schema constraints and checkpoint resume.
  ```bash
  python run_pipeline.py --stage test
  ```
* **Run Pass-1 Research (with optional limit)**: Scrapes all 100 apps (or limit to a small count).
  ```bash
  python run_pipeline.py --stage research --limit 3
  ```
* **Run Pass-2 Verification**: Generates independent validation comparisons and calculates accuracy.
  ```bash
  python run_pipeline.py --stage verify
  ```
* **Run Pattern Analysis & Site Generation**: Compiles distributions, cross-tabs, and builds `site/index.html`.
  ```bash
  python run_pipeline.py --stage analyze
  ```

---

## Checkpointing & Resumability
Web scraping and API calls are prone to network timeouts, rate limit caps, or system crashes. To solve this, our pipeline saves progress incrementally to `checkpoints/progress.json` after every single app. 
* If a run is interrupted, simply rerun the command.
* The pipeline will detect already-completed research and skip them, saving API credits and execution time.

---

## Where a Human Was Needed
While our agentic pipeline executes 95% of the data gathering, human validation is critical for quality assurance:
1. **Resolving Verification Diffs**: When the independent validation agent (Pass 2) disagreed with the research agent (Pass 1) on fields like `access_model` or `auth_methods`, a human checked the official site to declare the correct ground truth.
2. **Local Tool Exclusions**: CLI tools (like Mermaid CLI or Sherlock) do not fit standard hosted SaaS patterns. Human validation was needed to confirm these as `not-applicable` for hosted API credentials.
3. **Sandbox Credentials**: Creating test accounts to verify API surface breadth and verify sandbox tokens.

---

## Running Tests
Run tests directly using pytest:
```bash
pytest tests/ -v
```
