from __future__ import annotations
import json
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import anthropic
from activity_logger import log_action
from agents.mia import MiaAgent
from agents.zoe import ZoeAgent
from agents.bella import BellaAgent
from agents.lila import LilaAgent
from agents.nora import NoraAgent
from agents.roxy import RoxyAgent
from agents.emma import EmmaAgent
from agents.publish import PublishAgent, has_publish_failures
from checkpoint import pause
from config import Config
from job_store import save_job, load_recent_performance
from models.content_job import ContentJob, JobStatus
from tools.agent_tools import get_tool_definitions

_ROBIN_SYSTEM = """You are Robin, Chief of Staff at NayzFreedom.

You act directly on behalf of the owner. Every decision you make optimizes for maximum business benefit — reach, engagement, and brand growth — not just task completion.

Before recommending strategy, review past job performance data provided in context. If no performance data exists, proceed without it.

You coordinate Freedom Architects (Mia, Zoe, Bella, Lila, Nora, Roxy, Emma) through {pm_name}, the PM for {page_name}.

## Team workflow (follow this order):
1. run_mia — research trends
2. run_zoe — generate ideas (each idea has a content_type)
3. request_checkpoint (stage: "idea_selection") — show ideas, wait for user to pick one
4. run_bella — write content for the selected idea based on its content_type
5. After Bella completes, check job.content_type:
   - video, image, or infographic → run_lila (visual direction)
   - article → skip run_lila entirely, go directly to step 6
6. request_checkpoint (stage: "content_review") — show content and visual (if applicable) for approval
7. run_nora — QA review. If QA fails and retry count < max_retries, re-run the relevant agent.
8. request_checkpoint (stage: "qa_review") — show QA result
9. run_roxy and run_emma — call BOTH in the same response (they are independent and run in parallel); do not wait for one before calling the other
10. request_checkpoint (stage: "final_approval") — final sign-off before publishing
11. run_publish — publish to Meta (Facebook + Instagram). Pass schedule=true to post at Roxy's recommended time.

Never skip a checkpoint. After run_publish completes, declare the job complete.
"""


def _compact_messages(messages: list[dict], keep_recent_pairs: int = 3) -> list[dict]:
    """Trim Robin's older assistant text blocks to prevent context bloat.

    Keeps the initial brief and the most recent round-trips in full.
    Older assistant turns are compacted to tool_use blocks only (text
    reasoning is dropped). Tool results are already minimal so left as-is.
    """
    # Each round-trip = 2 messages: assistant turn + user turn (tool_results)
    if len(messages) < 1 + keep_recent_pairs * 2:
        return messages

    first = messages[:1]
    old = messages[1: -(keep_recent_pairs * 2)]
    recent = messages[-(keep_recent_pairs * 2):]

    compacted: list[dict] = []
    for msg in old:
        if msg["role"] == "assistant" and isinstance(msg["content"], list):
            # Keep tool_use blocks; drop text blocks to save tokens
            slim = [
                {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
                for b in msg["content"]
                if hasattr(b, "type") and b.type == "tool_use"
            ]
            compacted.append({"role": "assistant", "content": slim or msg["content"]})
        else:
            compacted.append(msg)

    return first + compacted + recent


class Orchestrator:
    def __init__(self, config: Config, safe_prep: bool = False):
        self.config = config
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        self.agents = {
            "mia": MiaAgent(config),
            "zoe": ZoeAgent(config),
            "bella": BellaAgent(config),
            "lila": LilaAgent(config),
            "nora": NoraAgent(config),
            "roxy": RoxyAgent(config),
            "emma": EmmaAgent(config),
            "publish": PublishAgent(config),
        }
        self._unattended: bool = False
        self.safe_prep = safe_prep

    def run(self, job: ContentJob, unattended: bool = False) -> ContentJob:
        self._unattended = unattended
        job.status = JobStatus.RUNNING
        log_action("orchestrator_start", {"job_id": job.id, "unattended": unattended})
        system_prompt = _ROBIN_SYSTEM.format(
            pm_name=job.pm.name,
            page_name=job.pm.page_name,
        )
        perf_summary = load_recent_performance(job.pm.page_name)
        first_message = f"Brief: {job.brief}\nPlatforms: {', '.join(job.platforms)}"
        if perf_summary:
            first_message = f"{perf_summary}\n\n{first_message}"
        messages: list[dict] = [{"role": "user", "content": first_message}]

        while True:
            response = self.client.messages.create(
                model="claude-opus-4-7",
                max_tokens=4096,
                system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                tools=get_tool_definitions(),
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                if has_publish_failures(job.publish_result):
                    job.status = JobStatus.FAILED
                elif self.safe_prep and not (
                    isinstance(job.publish_execution, dict)
                    and job.publish_execution.get("status") == "ready_to_publish"
                ):
                    job.status = JobStatus.AWAITING_APPROVAL
                else:
                    job.status = JobStatus.COMPLETED
                save_job(job)
                log_action("orchestrator_complete", {"job_id": job.id, "status": job.status.value})
                return job

            if response.stop_reason != "tool_use":
                job.status = JobStatus.FAILED
                save_job(job)
                raise RuntimeError(f"Unexpected stop_reason: {response.stop_reason}")

            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            checkpoint_blocks = [b for b in tool_blocks if b.name == "request_checkpoint"]
            agent_blocks = [b for b in tool_blocks if b.name != "request_checkpoint"]

            tool_results = []

            # Checkpoints run sequentially — they block for user input
            for block in checkpoint_blocks:
                result = self._dispatch(block.name, block.input, job)
                save_job(job)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })

            # Independent agent calls (e.g. run_roxy + run_emma) run concurrently
            if len(agent_blocks) > 1:
                results_map: dict[str, dict] = {}
                with ThreadPoolExecutor(max_workers=len(agent_blocks)) as executor:
                    future_to_block = {
                        executor.submit(self._dispatch, b.name, b.input, job): b
                        for b in agent_blocks
                    }
                    for future in as_completed(future_to_block):
                        blk = future_to_block[future]
                        results_map[blk.id] = future.result()
                save_job(job)
                for block in agent_blocks:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(results_map[block.id]),
                    })
            else:
                for block in agent_blocks:
                    result = self._dispatch(block.name, block.input, job)
                    save_job(job)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            messages = _compact_messages(messages)

    def _dispatch(self, tool_name: str, tool_input: dict, job: ContentJob) -> dict:
        if tool_name == "request_checkpoint":
            stage = tool_input.get("stage")
            options = tool_input.get("options", [])
            # For idea_selection, always build options from job.ideas so
            # Telegram shows numbered buttons even when Robin omits them.
            if stage == "idea_selection" and job.ideas:
                option_ideas = job.ideas
                if self._unattended and job.content_type:
                    matching = [i for i in job.ideas if i.content_type == job.content_type]
                    if matching:
                        option_ideas = matching
                options = [f"{i.number}: {i.title}" for i in option_ideas]
            log_action("request_checkpoint", {
                "job_id": job.id,
                "stage": stage,
                "options": options,
            })
            result = pause(
                stage=stage,
                summary=tool_input.get("summary"),
                options=options,
                job=job,
                unattended=self._unattended,
            )
            if stage == "idea_selection" and job.ideas is not None:
                try:
                    # Support both "1" and "1: Title" formats
                    decision_num = int(result.decision.split(":")[0].strip())
                    matched = next(
                        (i for i in job.ideas if i.number == decision_num), None
                    )
                    if matched is not None:
                        job.selected_idea = matched
                        job.content_type = matched.content_type
                except ValueError:
                    pass  # non-numeric input — leave selected_idea and content_type as-is
            return {"decision": result.decision}

        agent_name = tool_name.replace("run_", "")
        if agent_name not in self.agents:
            return {"error": f"Unknown tool: {tool_name}"}

        kwargs = {}
        if agent_name == "publish" and "schedule" in tool_input:
            kwargs["schedule"] = bool(tool_input["schedule"])
        if agent_name == "publish" and self.safe_prep:
            self._mark_safe_publish_handoff(job)
            log_action("safe_prep_publish_handoff", {
                "job_id": job.id,
                "stage": job.stage,
                "platforms": job.platforms,
            })
            return {"status": "safe_prep", "stage": job.stage}
        self.agents[agent_name].run(job, **kwargs)
        log_action("run_agent", {
            "job_id": job.id,
            "agent": agent_name,
            "stage": job.stage,
        })
        return {"status": "ok", "stage": job.stage}

    def _mark_safe_publish_handoff(self, job: ContentJob) -> ContentJob:
        """Record publish readiness without calling any external publisher API."""
        created_at = datetime.now(timezone.utc).isoformat()
        hashtags = job.growth_strategy.hashtags if job.growth_strategy else []
        caption = job.growth_strategy.caption if job.growth_strategy else ""
        package = {
            "status": "completed",
            "owners": ["Roxy", "Emma"],
            "caption": caption,
            "hashtags": hashtags,
            "faq_path": job.community_faq_path,
            "publish_notes": "Safe production prep stopped before external publish.",
            "created_at": created_at,
            "next_action": "Captain review required before dashboard handoff. Live publishing remains locked.",
            "source": "safe_prep_cli",
        }
        job.publish_package = package
        job.publish_execution = {
            "status": "ready_to_publish",
            "owners": ["Roxy", "Emma"],
            "platforms": list(job.platforms),
            "caption": caption,
            "hashtags": hashtags,
            "faq_path": job.community_faq_path,
            "video_path": job.video_path,
            "image_path": job.image_path,
            "created_at": created_at,
            "next_action": "Captain review required before dashboard handoff. Live publishing remains locked.",
            "source": "safe_prep_cli",
        }
        job.publish_result = {
            str(platform): {
                "status": "ready_to_publish",
                "dry_run": True,
                "reason": "Safe production prep stopped before external platform API call.",
            }
            for platform in job.platforms
        }
        job.stage = "ready_to_publish"
        return job
