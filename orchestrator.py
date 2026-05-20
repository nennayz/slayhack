from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from activity_logger import log_action
from agents.bella import BellaAgent
from agents.emma import EmmaAgent
from agents.lila import LilaAgent
from agents.mia import MiaAgent
from agents.nora import NoraAgent
from agents.publish import PublishAgent, has_publish_failures
from agents.roxy import RoxyAgent
from agents.zoe import ZoeAgent
from checkpoint import pause
from config import Config
from job_store import save_job
from models.content_job import CheckpointDecision, ContentJob, ContentType, Idea, JobStatus


class Orchestrator:
    def __init__(self, config: Config, safe_prep: bool = False):
        self.config = config
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

        self._run_step_if_needed(job, "run_mia", lambda j: j.trend_data is None)
        self._run_step_if_needed(job, "run_zoe", lambda j: j.ideas is None)
        if job.selected_idea is None:
            self._dispatch(
                "request_checkpoint",
                {
                    "stage": "idea_selection",
                    "summary": self._idea_selection_summary(job),
                    "options": self._idea_options(job),
                },
                job,
            )
            save_job(job)

        self._run_step_if_needed(job, "run_bella", lambda j: j.bella_output is None)
        self._run_step_if_needed(job, "run_lila", lambda j: self._needs_lila(j) and not self._visual_ready(j))

        if self._needs_content_review(job):
            self._dispatch(
                "request_checkpoint",
                {"stage": "content_review", "summary": self._content_review_summary(job)},
                job,
            )
            save_job(job)

        qa_terminal = self._run_qa_cycle(job)
        if qa_terminal:
            save_job(job)
            log_action("orchestrator_complete", {"job_id": job.id, "status": job.status.value})
            return job

        if job.growth_strategy is None or job.community_faq_path is None:
            self._run_parallel_post_production(job)
            save_job(job)

        if not self._checkpoint_recorded(job, "final_approval"):
            self._dispatch(
                "request_checkpoint",
                {"stage": "final_approval", "summary": self._final_approval_summary(job)},
                job,
            )
            save_job(job)

        if self.safe_prep:
            if not (
                isinstance(job.publish_execution, dict)
                and job.publish_execution.get("status") == "ready_to_publish"
            ):
                self._dispatch("run_publish", {"schedule": True}, job)
                save_job(job)
            job.status = JobStatus.AWAITING_APPROVAL
            log_action("orchestrator_complete", {"job_id": job.id, "status": job.status.value})
            return job

        if not self._publish_complete(job):
            self._dispatch("run_publish", {"schedule": True}, job)
            save_job(job)

        job.status = JobStatus.FAILED if has_publish_failures(job.publish_result) else JobStatus.COMPLETED
        save_job(job)
        log_action("orchestrator_complete", {"job_id": job.id, "status": job.status.value})
        return job

    def _run_step_if_needed(self, job: ContentJob, tool_name: str, predicate) -> None:
        if predicate(job):
            self._dispatch(tool_name, {}, job)
            save_job(job)

    def _run_qa_cycle(self, job: ContentJob) -> bool:
        while True:
            if job.qa_result is None:
                self._dispatch("run_nora", {}, job)
                save_job(job)

            if self._needs_qa_review(job):
                self._dispatch(
                    "request_checkpoint",
                    {"stage": "qa_review", "summary": self._qa_review_summary(job)},
                    job,
                )
                save_job(job)

            if job.qa_result is None:
                continue
            if job.qa_result.passed:
                return False
            if not job.qa_result.send_back_to or job.nora_retry_count >= job.pm.brand.nora_max_retries:
                job.status = JobStatus.AWAITING_APPROVAL
                return True

            self._prepare_retry(job, job.qa_result.send_back_to)
            if self._needs_content_review(job):
                self._dispatch(
                    "request_checkpoint",
                    {"stage": "content_review", "summary": self._content_review_summary(job)},
                    job,
                )
                save_job(job)

    def _prepare_retry(self, job: ContentJob, target: str) -> None:
        if target == "bella":
            job.bella_output = None
            job.visual_prompt = None
            job.image_path = None
            job.video_path = None
            self._dispatch("run_bella", {}, job)
            save_job(job)
            if self._needs_lila(job):
                self._dispatch("run_lila", {}, job)
                save_job(job)
        elif target == "lila":
            job.visual_prompt = None
            job.image_path = None
            job.video_path = None
            self._dispatch("run_lila", {}, job)
            save_job(job)
        job.qa_result = None

    def _run_parallel_post_production(self, job: ContentJob) -> None:
        clones = {
            "roxy": job.model_copy(deep=True),
            "emma": job.model_copy(deep=True),
        }
        completed: dict[str, ContentJob] = {}
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_name = {
                executor.submit(self._run_agent_job, name, clones[name]): name
                for name in ("roxy", "emma")
            }
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                completed[name] = future.result()

        roxy_job = completed["roxy"]
        emma_job = completed["emma"]
        job.growth_strategy = roxy_job.growth_strategy
        job.community_faq_path = emma_job.community_faq_path
        job.stage = "emma_done"

    def _run_agent_job(self, agent_name: str, job: ContentJob) -> ContentJob:
        return self.agents[agent_name].run(job)

    def _dispatch(self, tool_name: str, tool_input: dict, job: ContentJob) -> dict:
        if tool_name == "request_checkpoint":
            stage = tool_input.get("stage", "checkpoint")
            summary = tool_input.get("summary", "")
            options = tool_input.get("options", [])
            if stage == "idea_selection" and job.ideas:
                options = self._idea_options(job)
            checkpoint = pause(stage, summary, options, job, unattended=self._unattended)
            if stage == "idea_selection" and job.ideas is not None:
                decision_raw = str(checkpoint.decision).strip()
                selected_idea = self._select_idea(job.ideas, decision_raw, requested_content_type=job.content_type)
                if selected_idea is not None:
                    job.selected_idea = selected_idea
                    job.content_type = selected_idea.content_type
                    checkpoint.decision = str(selected_idea.number)
                    job.stage = "idea_selection"
            if not job.checkpoint_log or job.checkpoint_log[-1].stage != stage or job.checkpoint_log[-1].decision != checkpoint.decision:
                job.checkpoint_log.append(CheckpointDecision(stage=stage, decision=checkpoint.decision))
            log_action("checkpoint_recorded", {"job_id": job.id, "stage": stage, "decision": checkpoint.decision})
            return {"status": "paused", "stage": stage, "decision": checkpoint.decision}

        agent_name = tool_name.replace("run_", "")
        schedule = bool(tool_input.get("schedule", False))
        log_action("run_agent", {"job_id": job.id, "agent": agent_name, "stage_before": job.stage})
        if agent_name == "publish" and self.safe_prep:
            self._prepare_publish_handoff(job, schedule=schedule)
            return {"status": "safe_prep", "stage": job.stage}
        agent = self.agents[agent_name]
        result_job = agent.run(job, schedule=schedule)
        job.status = result_job.status
        return {"status": "ok", "stage": job.stage}

    def _prepare_publish_handoff(self, job: ContentJob, schedule: bool) -> None:
        requested_at = datetime.now(timezone.utc)
        growth = job.growth_strategy
        best_utc = growth.best_post_time_utc if growth else None
        best_thai = growth.best_post_time_thai if growth else None
        caption = growth.caption if growth else None
        hashtags = list(growth.hashtags) if growth else []
        editorial_guidance = growth.editorial_guidance if growth else {}
        job.publish_package = {
            "status": "completed",
            "requested_at": requested_at.isoformat(),
            "owners": ["Roxy", "Emma"],
            "caption": caption,
            "hashtags": hashtags,
            "best_post_time_utc": best_utc,
            "best_post_time_thai": best_thai,
            "community_faq_path": job.community_faq_path,
            "editorial_guidance": editorial_guidance,
        }
        next_action = (
            "Captain approved schedule handoff. Use dashboard scheduling or publish-only when ready."
            if schedule
            else "Captain approved manual publish handoff. Use dashboard scheduling or publish-only when ready."
        )
        job.publish_execution = {
            "status": "ready_to_publish",
            "owners": ["Roxy", "Emma"],
            "requested_at": requested_at.isoformat(),
            "schedule_requested": schedule,
            "best_post_time_utc": best_utc,
            "best_post_time_thai": best_thai,
            "next_action": next_action,
        }
        publish_payload = {
            str(platform): {
                "status": "ready_to_publish",
                "dry_run": True,
                "scheduled": schedule,
                "requested_at": requested_at.isoformat(),
            }
            for platform in job.platforms
        }
        job.publish_result = publish_payload
        job.stage = "ready_to_publish"

    def _idea_options(self, job: ContentJob) -> list[str]:
        if not job.ideas:
            return []
        return [f"{idea.number}. {idea.title}" for idea in job.ideas]

    def _select_idea(
        self,
        ideas: list[Idea],
        decision_raw: str,
        requested_content_type: ContentType | None = None,
    ) -> Idea | None:
        if self._unattended and requested_content_type is not None:
            for idea in ideas:
                if idea.content_type == requested_content_type:
                    return idea
        try:
            selected_num = int(decision_raw)
        except ValueError:
            return None
        return next((idea for idea in ideas if idea.number == selected_num), None)

    def _needs_lila(self, job: ContentJob) -> bool:
        return job.content_type in {ContentType.VIDEO, ContentType.IMAGE, ContentType.INFOGRAPHIC}

    def _visual_ready(self, job: ContentJob) -> bool:
        if job.content_type == ContentType.VIDEO:
            return bool(job.visual_prompt and job.video_path)
        if job.content_type == ContentType.IMAGE:
            return bool(job.visual_prompt and job.image_path)
        if job.content_type == ContentType.INFOGRAPHIC:
            return bool(job.visual_prompt)
        return True

    def _checkpoint_count(self, job: ContentJob, stage: str) -> int:
        return sum(1 for entry in job.checkpoint_log if entry.stage == stage)

    def _checkpoint_recorded(self, job: ContentJob, stage: str) -> bool:
        return self._checkpoint_count(job, stage) > 0

    def _needs_content_review(self, job: ContentJob) -> bool:
        return self._checkpoint_count(job, "content_review") <= job.nora_retry_count

    def _needs_qa_review(self, job: ContentJob) -> bool:
        return job.qa_result is not None and self._checkpoint_count(job, "qa_review") <= job.nora_retry_count

    def _publish_complete(self, job: ContentJob) -> bool:
        return job.stage == "publish_done" or (
            isinstance(job.publish_result, dict)
            and any(isinstance(value, dict) and value.get("status") in {"published", "scheduled"} for value in job.publish_result.values())
        )

    def _idea_selection_summary(self, job: ContentJob) -> str:
        lines = [f"Choose the strongest idea for: {job.brief}"]
        for idea in job.ideas or []:
            lines.append(f"{idea.number}. {idea.title} [{idea.content_type.value}] — {idea.hook}")
        return "\n".join(lines)

    def _content_review_summary(self, job: ContentJob) -> str:
        parts = [f"Review content for {job.pm.page_name}."]
        if job.content_type is not None:
            parts.append(f"Content type: {job.content_type.value}.")
        if job.visual_prompt:
            parts.append("Visual direction is ready.")
        if job.video_path:
            parts.append(f"Video draft: {job.video_path}")
        if job.image_path:
            parts.append(f"Image draft: {job.image_path}")
        return " ".join(parts)

    def _qa_review_summary(self, job: ContentJob) -> str:
        result = job.qa_result
        if result is None:
            return "QA result pending."
        if result.passed:
            return "QA passed. Approve to continue into growth + community packaging."
        details = ["QA failed."]
        if result.script_feedback:
            details.append(f"Script feedback: {result.script_feedback}")
        if result.visual_feedback:
            details.append(f"Visual feedback: {result.visual_feedback}")
        if result.send_back_to:
            details.append(f"Retry target: {result.send_back_to}")
        return " ".join(details)

    def _final_approval_summary(self, job: ContentJob) -> str:
        best_time = job.growth_strategy.best_post_time_thai if job.growth_strategy else "not set"
        faq_path = job.community_faq_path or "not created"
        return (
            f"Growth strategy and community FAQ are ready. Best Thai post time: {best_time}. "
            f"FAQ path: {faq_path}. Approve to publish."
        )
