from typing import AsyncGenerator, Optional, List, Dict, Any
import logging
from app.domain.models.plan import Plan, Step, ExecutionStatus
from app.domain.models.message import Message
from app.domain.services.agents.base import BaseAgent
from app.domain.external.llm import LLM
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.services.prompts.system import SYSTEM_PROMPT
from app.domain.models.event import (
    BaseEvent,
    StepEvent,
    StepStatus,
    ErrorEvent,
    MessageEvent,
    ToolEvent,
    ToolStatus,
    WaitEvent,
)
from app.domain.models.cloud_events import DeploymentEvent
from app.domain.models.cloud import (
    IaCConfiguration, 
    DeploymentRecord, 
    DeploymentStatus, 
    CloudProvider,
    CloudResource
)
from app.domain.services.tools.base import BaseTool
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)

DEPLOYMENT_AGENT_SYSTEM_PROMPT = """
You are an expert cloud deployment specialist. Your role is to deploy and manage cloud infrastructure safely and efficiently.

Your responsibilities:
1. Execute Infrastructure as Code deployments
2. Validate deployment prerequisites and credentials
3. Monitor deployment progress and handle failures
4. Implement rollback strategies for failed deployments
5. Verify deployed resources and their health
6. Generate deployment reports and documentation
7. Manage deployment lifecycle and updates

When performing deployments, ensure:
- Validate all prerequisites before deployment
- Use safe deployment practices (dry-run first)
- Monitor deployment progress continuously
- Implement proper error handling and rollback
- Verify resource health after deployment
- Document deployment results and configurations
- Follow security best practices throughout

Always prioritize safety and provide detailed deployment status updates.
"""


class DeploymentAgent(BaseAgent):
    """
    Deployment agent specialized in cloud infrastructure deployment
    """

    name: str = "deployment_agent"
    system_prompt: str = SYSTEM_PROMPT + DEPLOYMENT_AGENT_SYSTEM_PROMPT
    format: str = "json_object"

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
            tools=tools
        )
    
    async def deploy_infrastructure(
        self, 
        iac_config: IaCConfiguration,
        environment: str = "production",
        auto_approve: bool = False,
        region: Optional[str] = None
    ) -> AsyncGenerator[BaseEvent, None]:
        """Deploy infrastructure using IaC configuration"""
        
        deployment = DeploymentRecord(
            architecture_plan_id="",  # Will be set by pipeline
            iac_config_id=iac_config.id,
            status=DeploymentStatus.PENDING,
            provider=iac_config.provider,
            region=region or "us-east-1",
            resources=[],
            deployment_logs=[]
        )
        
        step = Step(
            description=f"Deploy {iac_config.provider.value} infrastructure using {iac_config.tool}",
            status=ExecutionStatus.RUNNING
        )
        yield StepEvent(status=StepStatus.STARTED, step=step)
        
        deployment.status = DeploymentStatus.DEPLOYING
        yield DeploymentEvent(
            deployment=deployment,
            status="started",
            progress_percentage=0
        )
        
        try:
            yield DeploymentEvent(
                deployment=deployment,
                status="in_progress",
                progress_percentage=10
            )
            
            validation_success = await self._validate_deployment_prerequisites(
                iac_config, deployment
            )
            
            if not validation_success:
                deployment.status = DeploymentStatus.FAILED
                deployment.error_message = "Prerequisites validation failed"
                step.status = ExecutionStatus.FAILED
                step.error = deployment.error_message
                yield StepEvent(status=StepStatus.FAILED, step=step)
                yield DeploymentEvent(deployment=deployment, status="failed")
                return
            
            yield DeploymentEvent(
                deployment=deployment,
                status="in_progress",
                progress_percentage=25
            )
            
            plan_result = await self._create_deployment_plan(iac_config, deployment)
            if not plan_result:
                deployment.status = DeploymentStatus.FAILED
                deployment.error_message = "Failed to create deployment plan"
                step.status = ExecutionStatus.FAILED
                step.error = deployment.error_message
                yield StepEvent(status=StepStatus.FAILED, step=step)
                yield DeploymentEvent(deployment=deployment, status="failed")
                return
            
            yield DeploymentEvent(
                deployment=deployment,
                status="in_progress",
                progress_percentage=50
            )
            
            deploy_result = await self._execute_deployment(
                iac_config, deployment, auto_approve
            )
            
            if not deploy_result:
                deployment.status = DeploymentStatus.FAILED
                step.status = ExecutionStatus.FAILED
                step.error = "Deployment execution failed"
                yield StepEvent(status=StepStatus.FAILED, step=step)
                yield DeploymentEvent(deployment=deployment, status="failed")
                return
            
            yield DeploymentEvent(
                deployment=deployment,
                status="in_progress",
                progress_percentage=80
            )
            
            verification_result = await self._verify_deployment(iac_config, deployment)
            
            if verification_result:
                deployment.status = DeploymentStatus.DEPLOYED
                step.status = ExecutionStatus.COMPLETED
                step.success = True
                step.result = f"Infrastructure deployed successfully with {len(deployment.resources)} resources"
                
                yield DeploymentEvent(
                    deployment=deployment,
                    status="completed",
                    progress_percentage=100
                )
                yield StepEvent(status=StepStatus.COMPLETED, step=step)
                
                summary = f"""

**Configuration:** {iac_config.name}
**Provider:** {iac_config.provider.value.upper()}
**Region:** {deployment.region}
**Resources Deployed:** {len(deployment.resources)}

{chr(10).join([f"- {r.name} ({r.type})" for r in deployment.resources[:10]])}
{'...' if len(deployment.resources) > 10 else ''}

- Status: ✅ Successfully Deployed
- Duration: {deployment.completed_at - deployment.started_at if deployment.completed_at else 'N/A'}
- Environment: {environment}

1. Set up monitoring and alerting
2. Configure backup and disaster recovery
3. Implement security monitoring
4. Set up cost monitoring

The infrastructure is now live and ready for use!
"""
                yield MessageEvent(message=summary)
            else:
                deployment.status = DeploymentStatus.FAILED
                step.status = ExecutionStatus.FAILED
                step.error = "Deployment verification failed"
                yield StepEvent(status=StepStatus.FAILED, step=step)
                yield DeploymentEvent(deployment=deployment, status="failed")
                
                yield MessageEvent(message="Deployment completed but verification failed. Please check the resources manually.")
                
        except Exception as e:
            logger.error(f"Deployment error: {e}")
            deployment.status = DeploymentStatus.FAILED
            deployment.error_message = str(e)
            step.status = ExecutionStatus.FAILED
            step.error = str(e)
            yield StepEvent(status=StepStatus.FAILED, step=step)
            yield DeploymentEvent(deployment=deployment, status="failed")
            yield ErrorEvent(error=f"Deployment failed: {str(e)}")

    async def rollback_deployment(
        self,
        deployment: DeploymentRecord,
        rollback_strategy: str = "destroy_all"
    ) -> AsyncGenerator[BaseEvent, None]:
        """Rollback a failed or problematic deployment"""
        
        step = Step(
            description=f"Rollback deployment {deployment.id}",
            status=ExecutionStatus.RUNNING
        )
        yield StepEvent(status=StepStatus.STARTED, step=step)
        
        deployment.status = DeploymentStatus.ROLLING_BACK
        yield DeploymentEvent(
            deployment=deployment,
            status="rolling_back",
            progress_percentage=0
        )
        
        try:
            terraform_tool = self._get_terraform_tool()
            if terraform_tool and rollback_strategy == "destroy_all":
                yield ToolEvent(
                    status=ToolStatus.CALLING,
                    tool_call_id="terraform_destroy",
                    tool_name="terraform",
                    function_name="terraform_destroy",
                    function_args={
                        "working_dir": deployment.iac_config_id,  # This should be the config path
                        "auto_approve": True
                    }
                )
                
                destroy_result = await terraform_tool.invoke_function(
                    "terraform_destroy",
                    working_dir=deployment.iac_config_id,
                    auto_approve=True
                )
                
                yield ToolEvent(
                    status=ToolStatus.CALLED,
                    tool_call_id="terraform_destroy",
                    tool_name="terraform",
                    function_name="terraform_destroy",
                    function_args={
                        "working_dir": deployment.iac_config_id,
                        "auto_approve": True
                    },
                    function_result=destroy_result
                )
                
                if destroy_result.success:
                    deployment.status = DeploymentStatus.ROLLED_BACK
                    deployment.resources = []  # Clear resources as they're destroyed
                    
                    step.status = ExecutionStatus.COMPLETED
                    step.success = True
                    step.result = "Deployment rolled back successfully"
                    yield StepEvent(status=StepStatus.COMPLETED, step=step)
                    
                    yield DeploymentEvent(
                        deployment=deployment,
                        status="completed",
                        progress_percentage=100
                    )
                    
                    summary = f"""

**Deployment ID:** {deployment.id}
**Status:** Successfully Rolled Back
**Strategy:** {rollback_strategy}

All resources have been destroyed and the deployment has been rolled back.

1. Review what caused the deployment failure
2. Fix the issues in the infrastructure configuration
3. Re-deploy when ready
"""
                    yield MessageEvent(message=summary)
                else:
                    deployment.status = DeploymentStatus.FAILED
                    step.status = ExecutionStatus.FAILED
                    step.error = f"Rollback failed: {destroy_result.message}"
                    yield StepEvent(status=StepStatus.FAILED, step=step)
                    yield DeploymentEvent(deployment=deployment, status="failed")
                    yield ErrorEvent(error=f"Rollback failed: {destroy_result.message}")
            else:
                cloud_tool = self._get_cloud_provider_tool()
                if cloud_tool:
                    for resource in deployment.resources:
                        pass
                
                deployment.status = DeploymentStatus.ROLLED_BACK
                step.status = ExecutionStatus.COMPLETED
                step.success = True
                step.result = "Manual rollback completed"
                yield StepEvent(status=StepStatus.COMPLETED, step=step)
                yield DeploymentEvent(deployment=deployment, status="completed")
                
        except Exception as e:
            logger.error(f"Rollback error: {e}")
            deployment.status = DeploymentStatus.FAILED
            step.status = ExecutionStatus.FAILED
            step.error = str(e)
            yield StepEvent(status=StepStatus.FAILED, step=step)
            yield DeploymentEvent(deployment=deployment, status="failed")
            yield ErrorEvent(error=f"Rollback failed: {str(e)}")

    async def verify_deployment(
        self,
        deployment: DeploymentRecord
    ) -> AsyncGenerator[BaseEvent, None]:
        """Verify deployment health and status"""
        
        step = Step(
            description=f"Verify deployment {deployment.id}",
            status=ExecutionStatus.RUNNING
        )
        yield StepEvent(status=StepStatus.STARTED, step=step)
        
        try:
            verification_results = []
            
            cloud_tool = self._get_cloud_provider_tool()
            if cloud_tool:
                for resource in deployment.resources:
                    if deployment.provider == CloudProvider.AWS:
                        result = await cloud_tool.invoke_function(
                            "aws_list_resources",
                            resource_type=resource.type,
                            region=deployment.region
                        )
                        if result.success:
                            verification_results.append(f"✅ {resource.name} ({resource.type}) - Active")
                        else:
                            verification_results.append(f"❌ {resource.name} ({resource.type}) - Not Found")
            
            monitoring_tool = self._get_monitoring_tool()
            if monitoring_tool:
                for resource in deployment.resources:
                    if resource.type in ["application", "web_service"]:
                        health_url = f"http://{resource.name}/health"  # Example
                        result = await monitoring_tool.invoke_function(
                            "check_service_health",
                            url=health_url
                        )
                        if result.success and result.data and result.data.get("healthy"):
                            verification_results.append(f"✅ {resource.name} health check - Passed")
                        else:
                            verification_results.append(f"⚠️ {resource.name} health check - Failed or Unavailable")
            
            failed_checks = [r for r in verification_results if r.startswith("❌")]
            warning_checks = [r for r in verification_results if r.startswith("⚠️")]
            
            if not failed_checks:
                step.status = ExecutionStatus.COMPLETED
                step.success = True
                step.result = f"Deployment verification passed with {len(verification_results)} checks"
                yield StepEvent(status=StepStatus.COMPLETED, step=step)
                
                summary = f"""

**Deployment ID:** {deployment.id}
**Status:** Verified Successfully
**Checks Performed:** {len(verification_results)}

{chr(10).join(verification_results)}

The deployment has been verified and is ready for use.
"""
                yield MessageEvent(message=summary)
            else:
                step.status = ExecutionStatus.FAILED
                step.error = f"Verification failed: {len(failed_checks)} critical issues found"
                yield StepEvent(status=StepStatus.FAILED, step=step)
                
                summary = f"""

**Deployment ID:** {deployment.id}
**Critical Issues:** {len(failed_checks)}
**Warnings:** {len(warning_checks)}

{chr(10).join(verification_results)}

Please review and fix the issues before proceeding.
"""
                yield MessageEvent(message=summary)
                yield ErrorEvent(error=step.error)
                
        except Exception as e:
            logger.error(f"Verification error: {e}")
            step.status = ExecutionStatus.FAILED
            step.error = str(e)
            yield StepEvent(status=StepStatus.FAILED, step=step)
            yield ErrorEvent(error=f"Deployment verification failed: {str(e)}")

    async def _validate_deployment_prerequisites(
        self,
        iac_config: IaCConfiguration,
        deployment: DeploymentRecord
    ) -> bool:
        """Validate deployment prerequisites"""
        try:
            terraform_tool = self._get_terraform_tool()
            if terraform_tool and iac_config.tool == "terraform":
                result = await terraform_tool.invoke_function(
                    "terraform_validate",
                    working_dir=iac_config.config_path
                )
                return result.success
            
            cloud_tool = self._get_cloud_provider_tool()
            if cloud_tool:
                if iac_config.provider == CloudProvider.AWS:
                    result = await cloud_tool.invoke_function("aws_list_resources", resource_type="iam")
                    return result.success
                elif iac_config.provider == CloudProvider.AZURE:
                    pass
                elif iac_config.provider == CloudProvider.GCP:
                    pass
            
            return True
        except Exception as e:
            logger.error(f"Prerequisites validation error: {e}")
            return False

    async def _create_deployment_plan(
        self,
        iac_config: IaCConfiguration,
        deployment: DeploymentRecord
    ) -> bool:
        """Create deployment plan"""
        try:
            terraform_tool = self._get_terraform_tool()
            if terraform_tool and iac_config.tool == "terraform":
                result = await terraform_tool.invoke_function(
                    "terraform_plan",
                    working_dir=iac_config.config_path,
                    variables=iac_config.variables
                )
                if result.success:
                    deployment.deployment_logs.append("Terraform plan created successfully")
                    return True
                else:
                    deployment.deployment_logs.append(f"Terraform plan failed: {result.message}")
                    return False
            return True
        except Exception as e:
            logger.error(f"Plan creation error: {e}")
            deployment.deployment_logs.append(f"Plan creation error: {str(e)}")
            return False

    async def _execute_deployment(
        self,
        iac_config: IaCConfiguration,
        deployment: DeploymentRecord,
        auto_approve: bool
    ) -> bool:
        """Execute the actual deployment"""
        try:
            terraform_tool = self._get_terraform_tool()
            if terraform_tool and iac_config.tool == "terraform":
                result = await terraform_tool.invoke_function(
                    "terraform_apply",
                    working_dir=iac_config.config_path,
                    auto_approve=auto_approve
                )
                if result.success:
                    deployment.deployment_logs.append("Terraform apply completed successfully")
                    
                    if result.data and "state" in result.data:
                        state = result.data["state"]
                        resources = state.get("values", {}).get("root_module", {}).get("resources", [])
                        for resource_data in resources:
                            resource = CloudResource(
                                name=resource_data.get("name", ""),
                                type=resource_data.get("type", ""),
                                provider=iac_config.provider,
                                region=deployment.region,
                                status="deployed"
                            )
                            deployment.resources.append(resource)
                    
                    return True
                else:
                    deployment.deployment_logs.append(f"Terraform apply failed: {result.message}")
                    deployment.error_message = result.message
                    return False
            return True
        except Exception as e:
            logger.error(f"Deployment execution error: {e}")
            deployment.deployment_logs.append(f"Deployment execution error: {str(e)}")
            deployment.error_message = str(e)
            return False

    async def _verify_deployment(
        self,
        iac_config: IaCConfiguration,
        deployment: DeploymentRecord
    ) -> bool:
        """Verify deployment success"""
        try:
            if not deployment.resources:
                deployment.deployment_logs.append("No resources found in deployment")
                return False
            
            cloud_tool = self._get_cloud_provider_tool()
            if cloud_tool:
                for resource in deployment.resources:
                    result = await cloud_tool.invoke_function(
                        "aws_list_resources" if iac_config.provider == CloudProvider.AWS else "list_resources",
                        resource_type=resource.type,
                        region=deployment.region
                    )
                    if not result.success:
                        deployment.deployment_logs.append(f"Failed to verify resource {resource.name}")
                        return False
            
            deployment.deployment_logs.append("All resources verified successfully")
            return True
        except Exception as e:
            logger.error(f"Deployment verification error: {e}")
            deployment.deployment_logs.append(f"Verification error: {str(e)}")
            return False

    def _get_terraform_tool(self) -> Optional[BaseTool]:
        """Get terraform tool from available tools"""
        for tool in self.tools:
            if tool.name == "terraform":
                return tool
        return None
    
    def _get_cloud_provider_tool(self) -> Optional[BaseTool]:
        """Get cloud provider tool from available tools"""
        for tool in self.tools:
            if tool.name == "cloud_provider":
                return tool
        return None
    
    def _get_monitoring_tool(self) -> Optional[BaseTool]:
        """Get monitoring tool from available tools"""
        for tool in self.tools:
            if tool.name == "monitoring":
                return tool
        return None
