from __future__ import annotations


def get_tool_definitions() -> list[dict]:
    return [
        {
            "name": "run_mia",
            "description": "Research current trends relevant to the brief using Brave Search. Call this first.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "run_zoe",
            "description": "Generate 5-7 content ideas based on Mia's trend research.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "run_bella",
            "description": "Write the Reels script for the selected idea.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "run_lila",
            "description": "Generate the visual prompt and create the key image for the Reel.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "run_nora",
            "description": "QA review the script and visual. Returns pass/fail with optional feedback.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "run_roxy",
            "description": "Generate hashtags, caption, and optimal posting time.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "run_emma",
            "description": "Prepare FAQ markdown with pre-written community responses.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "run_publish",
            "description": (
                "Publish the approved content to Facebook and Instagram via Meta Graph API. "
                "Call this as the final step after final_approval checkpoint. "
                "Pass schedule=true to post at Roxy's recommended time instead of immediately."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "schedule": {
                        "type": "boolean",
                        "description": "If true, schedule post at best_post_time_utc. Default false.",
                    }
                },
                "required": [],
            },
        },
        {
            "name": "run_scout",
            "description": "Scan 4 data sources (Brave, Google Trends, Reddit, Meta Ads) for niche opportunities. Call first in scout pipeline.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "dry_run": {"type": "boolean", "description": "If true, use mock data. Default false."}
                },
                "required": [],
            },
        },
        {
            "name": "run_analyst",
            "description": "Score and rank niche signals from Scout. Returns top 5 NicheOpportunity ranked by reach potential.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "dry_run": {"type": "boolean", "description": "If true, use mock data. Default false."}
                },
                "required": [],
            },
        },
        {
            "name": "run_architect",
            "description": "Generate project YAML files for the approved niche. Call only after Captain has set approved_niche.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "dry_run": {"type": "boolean", "description": "If true, log only. Do not write files. Default false."}
                },
                "required": [],
            },
        },
        {
            "name": "request_checkpoint",
            "description": (
                "Pause pipeline and ask the user for input or approval. "
                "Use at: (1) after Zoe to pick idea, (2) after Bella+Lila to review content, "
                "(3) after Nora QA, (4) before publishing."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "stage": {"type": "string", "description": "Checkpoint name, e.g. 'idea_selection'"},
                    "summary": {"type": "string", "description": "What to show the user"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Numbered options to present (optional)",
                    },
                },
                "required": ["stage", "summary"],
            },
        },
    ]
