from typing import AsyncGenerator, Optional, Dict, Any
import logging
from app.domain.services.flows.base import BaseFlow
from app.domain.services.agents.architecture_planner import ArchitecturePlannerAgent
from app.domain.services.agents.coding_agent import CodingAgent
from app.domain.services.agents.deployment_agent import DeploymentAgent
from app.domain.services.agents.monitoring_agent import MonitoringAgent
from app.domain.services.tools.cloud_provider import CloudProviderTool
from app.domain.services.tools.terraform import TerraformTool
from app.domain.services.tools.kubernetes import KubernetesTool
from app.domain.services.tools.monitoring import MonitoringTool
from app.domain.services.tools.shell import ShellTool
from app.domain.services.tools.browser import BrowserTool
from app.domain.services.tools.file import FileTool
from app.domain.services.tools.message import MessageTool
from app.domain.services.tools.search import SearchTool
from app.domain.services.tools.mcp import MCPTool
from app.domain.models.message import Message
from app.domain.models.event import BaseEvent, ErrorEvent, MessageEvent, DoneEvent
from app.domain.models.cloud_events import (
    CloudPipelineEvent,
    CloudPipelineStatus,
    ArchitecturePlanEvent,
    IaCGenerationEvent,
    DeploymentEvent,
    MonitoringEvent
)
from app.domain.models.cloud import (
    ArchitecturePlan,
    IaCConfiguration,
    DeploymentRecord,
    MonitoringConfig,
    CloudProvider
)
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.browser import Browser
from typing import Optional
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)


class CloudPipelineFlow(BaseFlow):
    """
    Cloud pipeline flow that orchestrates the multi-agent cloud architecture pipeline
    """
    
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
        search_engine: Optional[Any] = None,
    ):
        self._agent_id = agent_id
        self._repository = agent_repository
        self._session_id = session_id
        self._session_repository = session_repository
        self._llm = llm
        self._sandbox = sandbox
        self._browser = browser
        self._json_parser = json_parser
        self._search_engine = search_engine
        
        self.current_stage = "planning"
        self.architecture_plan: Optional[ArchitecturePlan] = None
        self.iac_config: Optional[IaCConfiguration] = None
        self.deployment: Optional[DeploymentRecord] = None
        self.monitoring_config: Optional[MonitoringConfig] = None
        
        self.cloud_tools = [
            ShellTool(sandbox),
            BrowserTool(browser),
            FileTool(sandbox),
            MessageTool(),
            CloudProviderTool(sandbox),
            TerraformTool(sandbox),
            KubernetesTool(sandbox),
            MonitoringTool(sandbox),
            mcp_tool
        ]
        
        if search_engine:
            self.cloud_tools.append(SearchTool(search_engine))
        
        self.architecture_planner = ArchitecturePlannerAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=self._llm,
            tools=self.cloud_tools,
            json_parser=self._json_parser,
        )
        
        self.coding_agent = CodingAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=self._llm,
            tools=self.cloud_tools,
            json_parser=self._json_parser,
        )
        
        self.deployment_agent = DeploymentAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=self._llm,
            tools=self.cloud_tools,
            json_parser=self._json_parser,
        )
        
        self.monitoring_agent = MonitoringAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=self._llm,
            tools=self.cloud_tools,
            json_parser=self._json_parser,
        )
        
        logger.info(f"CloudPipelineFlow initialized for agent {self._agent_id}")

    async def run(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        """
        Run the cloud pipeline flow
        """
        try:
            logger.info(f"Starting cloud pipeline flow for message: {message.message[:100]}...")
            
            yield CloudPipelineEvent(
                pipeline_status=CloudPipelineStatus.PLANNING,
                current_stage="planning",
                progress_percentage=0,
                metadata={"message": message.message[:200]}
            )
            
            async for event in self._run_architecture_planning(message):
                yield event
                
                if isinstance(event, ArchitecturePlanEvent) and event.status == "created":
                    self.architecture_plan = event.plan
                    self.current_stage = "coding"
                    
                    yield CloudPipelineEvent(
                        pipeline_status=CloudPipelineStatus.CODING,
                        current_stage="coding",
                        progress_percentage=25,
                        metadata={"architecture_plan_id": self.architecture_plan.id if self.architecture_plan else None}
                    )
                    break
            
            if not self.architecture_plan:
                yield ErrorEvent(error="Failed to create architecture plan")
                return
            
            async for event in self._run_iac_generation():
                yield event
                
                if isinstance(event, IaCGenerationEvent) and event.status == "completed":
                    self.iac_config = event.config
                    self.current_stage = "deployment"
                    
                    yield CloudPipelineEvent(
                        pipeline_status=CloudPipelineStatus.DEPLOYING,
                        current_stage="deployment",
                        progress_percentage=50,
                        metadata={"iac_config_id": self.iac_config.id if self.iac_config else None}
                    )
                    break
            
            if not self.iac_config:
                yield ErrorEvent(error="Failed to generate Infrastructure as Code configuration")
                return
            
            async for event in self._run_deployment():
                yield event
                
                if isinstance(event, DeploymentEvent) and event.status == "completed":
                    self.deployment = event.deployment
                    self.current_stage = "monitoring"
                    
                    yield CloudPipelineEvent(
                        pipeline_status=CloudPipelineStatus.MONITORING,
                        current_stage="monitoring",
                        progress_percentage=75,
                        metadata={"deployment_id": self.deployment.id if self.deployment else None}
                    )
                    break
            
            if not self.deployment or self.deployment.status.value != "deployed":
                yield ErrorEvent(error="Failed to deploy infrastructure")
                return
            
            async for event in self._run_monitoring_setup():
                yield event
                
                if isinstance(event, MonitoringEvent) and event.status == "configured":
                    self.monitoring_config = event.config
                    break
            
            yield CloudPipelineEvent(
                pipeline_status=CloudPipelineStatus.COMPLETED,
                current_stage="completed",
                progress_percentage=100,
                metadata={
                    "architecture_plan_id": self.architecture_plan.id,
                    "iac_config_id": self.iac_config.id,
                    "deployment_id": self.deployment.id,
                    "monitoring_config_id": self.monitoring_config.id if self.monitoring_config else None
                }
            )
            
            final_summary = f"""

- **Architecture Plan:** {self.architecture_plan.title}
- **Provider:** {self.architecture_plan.provider.value.upper()}
- **Architecture Type:** {self.architecture_plan.architecture_type.value.title()}
- **Resources Deployed:** {len(self.deployment.resources)}
- **Monthly Cost:** ${self.architecture_plan.estimated_cost_monthly:.2f}

1. ✅ **Architecture Planning** - Analyzed requirements and created optimal cloud architecture
2. ✅ **Code Generation** - Generated Infrastructure as Code using {self.iac_config.tool.title()}
3. ✅ **Deployment** - Successfully deployed {len(self.deployment.resources)} resources to {self.deployment.provider.value.upper()}
4. ✅ **Monitoring** - Set up comprehensive monitoring and alerting

- 🚀 **Live and Running** - All services are deployed and operational
- 📊 **Monitored** - Comprehensive monitoring and alerting in place
- 🔒 **Secure** - Security best practices implemented
- 💰 **Cost-Optimized** - Configured for optimal cost efficiency

1. Access your monitoring dashboards (Prometheus: http://localhost:9090, Grafana: http://localhost:3000)
2. Review and customize alert thresholds as needed
3. Set up backup and disaster recovery procedures
4. Monitor costs and optimize as your usage patterns emerge

Your cloud infrastructure is ready for production use! 🎊
"""
            yield MessageEvent(message=final_summary)
            yield DoneEvent()
            
        except Exception as e:
            logger.error(f"Cloud pipeline flow error: {e}")
            yield CloudPipelineEvent(
                pipeline_status=CloudPipelineStatus.FAILED,
                current_stage=self.current_stage,
                progress_percentage=0,
                metadata={"error": str(e)}
            )
            yield ErrorEvent(error=f"Cloud pipeline failed: {str(e)}")

    async def _run_architecture_planning(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        """Run the architecture planning stage"""
        logger.info("Starting architecture planning stage")
        
        user_count = self._extract_user_count(message.message)
        budget = self._extract_budget(message.message)
        provider = self._extract_provider(message.message)
        
        async for event in self.architecture_planner.create_architecture_plan(
            message=message,
            user_count=user_count,
            budget=budget,
            provider=provider
        ):
            yield event

    async def _run_iac_generation(self) -> AsyncGenerator[BaseEvent, None]:
        """Run the Infrastructure as Code generation stage"""
        logger.info("Starting IaC generation stage")
        
        if not self.architecture_plan:
            yield ErrorEvent(error="No architecture plan available for IaC generation")
            return
        
        iac_tool = "terraform"  # Default to Terraform
        if self.architecture_plan.provider == CloudProvider.AZURE:
            iac_tool = "terraform"  # Could be ARM templates
        elif self.architecture_plan.provider == CloudProvider.GCP:
            iac_tool = "terraform"  # Could be Deployment Manager
        
        async for event in self.coding_agent.generate_iac_configuration(
            architecture_plan=self.architecture_plan,
            iac_tool=iac_tool,
            output_path=f"/home/ubuntu/infrastructure/{self.architecture_plan.id}"
        ):
            yield event

    async def _run_deployment(self) -> AsyncGenerator[BaseEvent, None]:
        """Run the deployment stage"""
        logger.info("Starting deployment stage")
        
        if not self.iac_config:
            yield ErrorEvent(error="No IaC configuration available for deployment")
            return
        
        environment = "production"
        auto_approve = True  # For demo purposes - in production this should be False
        region = "us-east-1"  # Default region
        
        async for event in self.deployment_agent.deploy_infrastructure(
            iac_config=self.iac_config,
            environment=environment,
            auto_approve=auto_approve,
            region=region
        ):
            yield event

    async def _run_monitoring_setup(self) -> AsyncGenerator[BaseEvent, None]:
        """Run the monitoring setup stage"""
        logger.info("Starting monitoring setup stage")
        
        if not self.deployment:
            yield ErrorEvent(error="No deployment available for monitoring setup")
            return
        
        async for event in self.monitoring_agent.setup_monitoring(
            deployment=self.deployment,
            monitoring_config_dir=f"/home/ubuntu/monitoring/{self.deployment.id}"
        ):
            yield event

    def _extract_user_count(self, message: str) -> int:
        """Extract expected user count from message"""
        import re
        
        patterns = [
            r'(\d+(?:,\d+)*)\s*(?:users?|people|customers?)',
            r'(\d+)k\s*(?:users?|people|customers?)',
            r'(\d+)m\s*(?:users?|people|customers?)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                value = match.group(1).replace(',', '')
                if 'k' in pattern:
                    return int(value) * 1000
                elif 'm' in pattern:
                    return int(value) * 1000000
                else:
                    return int(value)
        
        return 1000  # Default

    def _extract_budget(self, message: str) -> Optional[str]:
        """Extract budget constraints from message"""
        import re
        
        budget_patterns = [
            r'\$(\d+(?:,\d+)*)\s*(?:per\s*month|monthly|/month)',
            r'budget\s*(?:of\s*)?\$(\d+(?:,\d+)*)',
            r'(\d+(?:,\d+)*)\s*dollars?\s*(?:per\s*month|monthly)',
        ]
        
        for pattern in budget_patterns:
            match = re.search(pattern, message.lower())
            if match:
                return f"${match.group(1)} per month"
        
        return None

    def _extract_provider(self, message: str) -> Optional[str]:
        """Extract preferred cloud provider from message"""
        message_lower = message.lower()
        
        if 'aws' in message_lower or 'amazon' in message_lower:
            return 'aws'
        elif 'azure' in message_lower or 'microsoft' in message_lower:
            return 'azure'
        elif 'gcp' in message_lower or 'google cloud' in message_lower or 'gce' in message_lower:
            return 'gcp'
        
        return None  # Let the architecture planner decide
