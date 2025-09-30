import logging
from typing import AsyncGenerator, Optional
from app.domain.services.flows.base import BaseFlow
from app.domain.models.message import Message
from app.domain.models.event import BaseEvent, DoneEvent, MessageEvent, TitleEvent
from app.domain.models.cloud_events import (
    CloudPipelineEvent, CloudPipelineStatus
)
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.browser import Browser
from app.domain.external.search import SearchEngine
from app.domain.utils.json_parser import JsonParser
from app.domain.services.agents.planner import ArchitecturePlannerAgent
from app.domain.services.agents.execution import IaCExecutionAgent, DeploymentAgent, MonitoringAgent
from app.domain.services.tools.mcp import MCPTool

logger = logging.getLogger(__name__)


class CloudPipelineFlow(BaseFlow):
    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        session_id: str,
        session_repository: SessionRepository,
        llm: LLM,
        sandbox: Sandbox,
        browser: Browser,
        json_parser: JsonParser,
        mcp_tool: MCPTool,
        search_engine: Optional[SearchEngine] = None,
    ):
        self._agent_id = agent_id
        self._repository = agent_repository
        self._session_id = session_id
        self._session_repository = session_repository
        self._done = False

        tools = [mcp_tool]  # base tool always present
        # Reuse same tool set assembled in PlanActFlow by importing on demand to avoid cycles
        from app.domain.services.tools.shell import ShellTool
        from app.domain.services.tools.browser import BrowserTool
        from app.domain.services.tools.file import FileTool
        from app.domain.services.tools.message import MessageTool
        from app.domain.services.tools.search import SearchTool
        from app.domain.services.tools.cloud_provider import CloudProviderTool
        from app.domain.services.tools.terraform import TerraformTool
        from app.domain.services.tools.kubernetes import KubernetesTool
        from app.domain.services.tools.monitoring import MonitoringTool
        from app.domain.services.tools.architecture_planning import ArchitecturePlanningTool
        from app.domain.services.tools.iac_coding import IaCCodingTool

        tools.extend([
            ShellTool(sandbox),
            BrowserTool(browser),
            FileTool(sandbox),
            MessageTool(),
            CloudProviderTool(sandbox),
            TerraformTool(sandbox),
            KubernetesTool(sandbox),
            MonitoringTool(sandbox),
            ArchitecturePlanningTool(sandbox),
            IaCCodingTool(sandbox),
        ])
        if search_engine:
            tools.append(SearchTool(search_engine))

        self.planner = ArchitecturePlannerAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
        )
        self.coder = IaCExecutionAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
        )
        self.deployer = DeploymentAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
        )
        self.monitor = MonitoringAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
        )
        self._stage = "planning"

    async def run(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        # Stage: Planning
        logger.info("Cloud pipeline: planning")
        yield CloudPipelineEvent(pipeline_status=CloudPipelineStatus.PLANNING, current_stage="planning")
        last_plan = None
        last_mermaid = None
        async for event in self.planner.create_plan(message):
            # capture mermaid from planning tool output
            if getattr(event, 'type', '') == 'tool' and getattr(event, 'function_name', '') == 'create_architecture_plan' and getattr(event, 'status', None):
                try:
                    if event.function_result and hasattr(event.function_result, 'data'):
                        last_mermaid = event.function_result.data.get('mermaid')
                except Exception:
                    pass
            if hasattr(event, 'plan'):
                # attach mermaid if available
                try:
                    if last_mermaid:
                        event.plan.mermaid = last_mermaid
                except Exception:
                    pass
                last_plan = event.plan.model_dump()
            yield event

        if not last_plan:
            # No plan yet; ask user for requirements via a clear assistant message then pause
            ask = "Please provide architecture requirements JSON with fields: provider (aws|azure|gcp), architecture_type (microservices|serverless|monolith), users (int), budget (USD/month). Example: {\"provider\":\"aws\",\"architecture_type\":\"microservices\",\"users\":1000,\"budget\":500}."
            yield MessageEvent(message=ask)
            yield WaitEvent()
            return
        self._stage = "coding"

        # Stage: IaC Generation (one execution step message-chained)
        logger.info("Cloud pipeline: iac coding")
        yield CloudPipelineEvent(pipeline_status=CloudPipelineStatus.CODING, current_stage="iac")
        gen_msg = Message(message="Generate IaC from latest plan and write to /home/ubuntu/iac. Respond in JSON format.")
        async for event in self.coder.execute(gen_msg.message, format="json_object"):
            # If tool call lacks architecture_plan, inject from last planning output
            if event.type == "tool" and event.status.name.lower() == "calling" and event.function_name == "generate_iac_from_plan":
                if last_plan:
                    args = event.function_args or {}
                    if "architecture_plan" not in args:
                        args["architecture_plan"] = last_plan
                        event.function_args = args
            # Pass-through; ExecutionAgent.execute yields Tool/Message events
            yield event

        # Stage: Deployment (guarded by flag)
        from app.core.config import get_settings
        settings = get_settings()
        if settings.cloud_tools_allow_deploy:
            logger.info("Cloud pipeline: deployment")
            yield CloudPipelineEvent(pipeline_status=CloudPipelineStatus.DEPLOYING, current_stage="deploy")
            deploy_msg = Message(message="Plan and apply deployment using terraform in /home/ubuntu/iac. Respond in JSON format.")
            async for event in self.deployer.execute(deploy_msg.message, format="json_object"):
                yield event

        # Stage: Monitoring
        logger.info("Cloud pipeline: monitoring")
        yield CloudPipelineEvent(pipeline_status=CloudPipelineStatus.MONITORING, current_stage="monitor")
        mon_msg = Message(message="Setup monitoring for deployed services and report health. Respond in JSON format.")
        async for event in self.monitor.execute(mon_msg.message, format="json_object"):
            yield event

        # Done
        yield CloudPipelineEvent(pipeline_status=CloudPipelineStatus.COMPLETED, current_stage="done")
        yield DoneEvent()
        self._done = True

    def is_done(self) -> bool:
        return self._done

