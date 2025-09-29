from typing import Dict, Any, List, AsyncGenerator, Optional
import json
import logging
from app.domain.models.plan import Plan, Step
from app.domain.models.message import Message
from app.domain.services.agents.base import BaseAgent
from app.domain.models.memory import Memory
from app.domain.external.llm import LLM
from app.domain.services.prompts.system import SYSTEM_PROMPT
from app.domain.models.event import (
    BaseEvent,
    PlanEvent,
    PlanStatus,
    ErrorEvent,
    MessageEvent,
    DoneEvent,
)
from app.domain.models.cloud_events import ArchitecturePlanEvent, CostEstimateEvent
from app.domain.models.cloud import ArchitecturePlan, CloudProvider, ArchitectureType, CloudResource
from app.domain.external.sandbox import Sandbox
from app.domain.services.tools.base import BaseTool
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)

ARCHITECTURE_PLANNER_SYSTEM_PROMPT = """
You are an expert cloud architecture planner. Your role is to analyze user requirements and create comprehensive cloud architecture plans.

Your responsibilities:
1. Analyze user inputs (GitHub repositories, documents, cost requirements, user counts)
2. Recommend appropriate cloud architecture patterns (microservices, monolith, serverless, etc.)
3. Select optimal cloud provider and services based on requirements
4. Estimate costs and resource requirements
5. Create detailed architecture plans with resource specifications
6. Generate architecture diagrams and documentation

When creating architecture plans, consider:
- Scalability requirements based on expected user count
- Cost optimization strategies
- Security best practices
- High availability and disaster recovery
- Performance requirements
- Compliance and regulatory requirements

Always provide detailed explanations for your architectural decisions and include cost breakdowns.
"""

CREATE_ARCHITECTURE_PLAN_PROMPT = """
Based on the user's requirements, create a comprehensive cloud architecture plan.

User Requirements:
{message}

Attached Files/Repositories:
{attachments}

Expected User Count: {user_count}
Budget Constraints: {budget}
Preferred Cloud Provider: {provider}

Please analyze the requirements and create a detailed architecture plan including:
1. Recommended architecture type (microservices, monolith, serverless, etc.)
2. Cloud provider selection and justification
3. Detailed resource specifications
4. Cost estimates (monthly and yearly)
5. Scalability considerations
6. Security recommendations
7. Deployment strategy

Return your response as a JSON object with the following structure:
{{
    "title": "Architecture Plan Title",
    "description": "Detailed description of the architecture",
    "provider": "aws|azure|gcp",
    "architecture_type": "microservices|monolith|serverless|container|hybrid",
    "estimated_users": number,
    "estimated_cost_monthly": number,
    "resources": [
        {{
            "name": "resource-name",
            "type": "ec2|s3|rds|lambda|etc",
            "provider": "aws|azure|gcp",
            "region": "region-name",
            "status": "planned",
            "cost_estimate": number,
            "tags": {{}},
            "specifications": {{
                "instance_type": "t3.medium",
                "storage": "100GB",
                "memory": "4GB",
                "cpu": "2 vCPU"
            }}
        }}
    ],
    "requirements": {{
        "scalability": "description",
        "security": "requirements",
        "compliance": "standards",
        "performance": "requirements"
    }},
    "deployment_strategy": "description",
    "monitoring_strategy": "description"
}}
"""

UPDATE_ARCHITECTURE_PLAN_PROMPT = """
Update the existing architecture plan based on new requirements or feedback.

Current Architecture Plan:
{current_plan}

Update Requirements:
{update_message}

Please update the architecture plan considering the new requirements while maintaining consistency with existing decisions where appropriate.

Return the updated plan as a JSON object with the same structure as the original plan.
"""


class ArchitecturePlannerAgent(BaseAgent):
    """
    Architecture planner agent for cloud infrastructure planning
    """

    name: str = "architecture_planner"
    system_prompt: str = SYSTEM_PROMPT + ARCHITECTURE_PLANNER_SYSTEM_PROMPT
    format: Optional[str] = "json_object"
    tool_choice: Optional[str] = "none"

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        llm: LLM,
        tools: List[BaseTool],
        json_parser: JsonParser,
    ):
        super().__init__(
            agent_id=agent_id,
            agent_repository=agent_repository,
            llm=llm,
            json_parser=json_parser,
            tools=tools,
        )

    async def create_architecture_plan(
        self, 
        message: Message,
        user_count: int = 1000,
        budget: Optional[str] = None,
        provider: Optional[str] = None
    ) -> AsyncGenerator[BaseEvent, None]:
        """Create architecture plan from user requirements"""
        
        formatted_message = CREATE_ARCHITECTURE_PLAN_PROMPT.format(
            message=message.message,
            attachments="\n".join(message.attachments),
            user_count=user_count,
            budget=budget or "Not specified",
            provider=provider or "Not specified"
        )
        
        async for event in self.execute(formatted_message):
            if isinstance(event, MessageEvent):
                logger.info(f"Architecture planner response: {event.message[:200]}...")
                try:
                    parsed_response = await self.json_parser.parse(event.message)
                    
                    if not isinstance(parsed_response, dict):
                        raise ValueError("Expected JSON object from architecture plan response")
                    
                    architecture_plan = ArchitecturePlan(
                        title=parsed_response.get("title", "Cloud Architecture Plan"),
                        description=parsed_response.get("description", ""),
                        provider=CloudProvider(parsed_response.get("provider", "aws")),
                        architecture_type=ArchitectureType(parsed_response.get("architecture_type", "microservices")),
                        estimated_users=parsed_response.get("estimated_users", user_count),
                        estimated_cost_monthly=parsed_response.get("estimated_cost_monthly"),
                        requirements=parsed_response.get("requirements", {}),
                        resources=[]
                    )
                    
                    for resource_data in parsed_response.get("resources", []):
                        resource = CloudResource(
                            name=resource_data.get("name", ""),
                            type=resource_data.get("type", ""),
                            provider=CloudProvider(resource_data.get("provider", "aws")),
                            region=resource_data.get("region", "us-east-1"),
                            status=resource_data.get("status", "planned"),
                            cost_estimate=resource_data.get("cost_estimate"),
                            tags=resource_data.get("tags", {})
                        )
                        architecture_plan.resources.append(resource)
                    
                    yield ArchitecturePlanEvent(
                        plan=architecture_plan,
                        status="created"
                    )
                    
                    if architecture_plan.estimated_cost_monthly:
                        yield CostEstimateEvent(
                            monthly_cost=architecture_plan.estimated_cost_monthly,
                            yearly_cost=architecture_plan.estimated_cost_monthly * 12,
                            breakdown={
                                resource.name: resource.cost_estimate or 0 
                                for resource in architecture_plan.resources
                            }
                        )
                    
                    summary = f"""

**Provider:** {architecture_plan.provider.value.upper()}
**Architecture Type:** {architecture_plan.architecture_type.value.title()}
**Estimated Users:** {architecture_plan.estimated_users:,}
**Monthly Cost:** ${architecture_plan.estimated_cost_monthly:.2f}

{chr(10).join([f"- {r.name} ({r.type})" for r in architecture_plan.resources[:5]])}
{'...' if len(architecture_plan.resources) > 5 else ''}

1. Review and approve the architecture plan
2. Generate Infrastructure as Code (IaC) configuration
3. Deploy the infrastructure
4. Set up monitoring and alerting

The architecture plan has been optimized for your requirements and includes cost estimates, scalability considerations, and security recommendations.
"""
                    yield MessageEvent(message=summary)
                    
                except Exception as e:
                    logger.error(f"Error parsing architecture plan response: {e}")
                    yield ErrorEvent(error=f"Failed to parse architecture plan: {str(e)}")
            else:
                yield event

    async def update_architecture_plan(
        self, 
        current_plan: ArchitecturePlan, 
        update_message: Message
    ) -> AsyncGenerator[BaseEvent, None]:
        """Update existing architecture plan"""
        
        formatted_message = UPDATE_ARCHITECTURE_PLAN_PROMPT.format(
            current_plan=current_plan.model_dump_json(),
            update_message=update_message.message
        )
        
        async for event in self.execute(formatted_message):
            if isinstance(event, MessageEvent):
                logger.info(f"Architecture plan update response: {event.message[:200]}...")
                try:
                    parsed_response = await self.json_parser.parse(event.message)
                    
                    if not isinstance(parsed_response, dict):
                        raise ValueError("Expected JSON object from architecture plan update response")
                    
                    current_plan.title = parsed_response.get("title", current_plan.title)
                    current_plan.description = parsed_response.get("description", current_plan.description)
                    current_plan.provider = CloudProvider(parsed_response.get("provider", current_plan.provider))
                    current_plan.architecture_type = ArchitectureType(parsed_response.get("architecture_type", current_plan.architecture_type))
                    current_plan.estimated_users = parsed_response.get("estimated_users", current_plan.estimated_users)
                    current_plan.estimated_cost_monthly = parsed_response.get("estimated_cost_monthly", current_plan.estimated_cost_monthly)
                    current_plan.requirements = parsed_response.get("requirements", current_plan.requirements)
                    
                    current_plan.resources = []
                    for resource_data in parsed_response.get("resources", []):
                        resource = CloudResource(
                            name=resource_data.get("name", ""),
                            type=resource_data.get("type", ""),
                            provider=CloudProvider(resource_data.get("provider", "aws")),
                            region=resource_data.get("region", "us-east-1"),
                            status=resource_data.get("status", "planned"),
                            cost_estimate=resource_data.get("cost_estimate"),
                            tags=resource_data.get("tags", {})
                        )
                        current_plan.resources.append(resource)
                    
                    yield ArchitecturePlanEvent(
                        plan=current_plan,
                        status="updated"
                    )
                    
                    if current_plan.estimated_cost_monthly:
                        yield CostEstimateEvent(
                            monthly_cost=current_plan.estimated_cost_monthly,
                            yearly_cost=current_plan.estimated_cost_monthly * 12,
                            breakdown={
                                resource.name: resource.cost_estimate or 0 
                                for resource in current_plan.resources
                            }
                        )
                    
                    summary = f"""

**Updated Provider:** {current_plan.provider.value.upper()}
**Updated Architecture Type:** {current_plan.architecture_type.value.title()}
**Updated Monthly Cost:** ${current_plan.estimated_cost_monthly:.2f}

The architecture plan has been updated based on your requirements. Please review the changes and proceed with the next steps if satisfied.

1. Review the updated architecture plan
2. Generate updated Infrastructure as Code (IaC) configuration
3. Deploy or update the infrastructure
4. Update monitoring configuration
"""
                    yield MessageEvent(message=summary)
                    
                except Exception as e:
                    logger.error(f"Error parsing architecture plan update: {e}")
                    yield ErrorEvent(error=f"Failed to update architecture plan: {str(e)}")
            else:
                yield event

    async def analyze_repository(self, repository_path: str) -> AsyncGenerator[BaseEvent, None]:
        """Analyze a code repository to understand architecture requirements"""
        
        analysis_message = f"""
Analyze the code repository at {repository_path} to understand the application architecture and requirements.

Please examine:
1. Application type and technology stack
2. Dependencies and frameworks used
3. Database requirements
4. API endpoints and services
5. Static assets and storage needs
6. Scalability patterns already implemented
7. Security considerations
8. Deployment configuration (if any)

Based on your analysis, provide recommendations for cloud architecture including:
- Suitable cloud services for each component
- Scalability strategies
- Security recommendations
- Cost optimization opportunities

Return your analysis as a JSON object with detailed findings and recommendations.
"""
        
        message = Message(message=analysis_message, attachments=[repository_path])
        
        async for event in self.execute(analysis_message):
            if isinstance(event, MessageEvent):
                logger.info(f"Repository analysis response: {event.message[:200]}...")
                try:
                    parsed_response = await self.json_parser.parse(event.message)
                    
                    if not isinstance(parsed_response, dict):
                        parsed_response = {}
                    
                    analysis_summary = f"""

{parsed_response.get('technology_stack', 'Not specified')}

{parsed_response.get('architecture_recommendations', 'Not specified')}

{parsed_response.get('resource_requirements', 'Not specified')}

{parsed_response.get('security_considerations', 'Not specified')}

{parsed_response.get('cost_optimization', 'Not specified')}

The repository has been analyzed and architecture recommendations are ready. You can now proceed to create a detailed architecture plan based on these findings.
"""
                    yield MessageEvent(message=analysis_summary)
                    
                except Exception as e:
                    logger.error(f"Error parsing repository analysis: {e}")
                    yield ErrorEvent(error=f"Failed to analyze repository: {str(e)}")
            else:
                yield event
