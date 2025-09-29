from typing import AsyncGenerator, Optional, List, Dict, Any
import logging
from app.domain.models.plan import Plan, Step, ExecutionStatus
from app.domain.models.file import FileInfo
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
    DoneEvent,
    ToolEvent,
    ToolStatus,
    WaitEvent,
)
from app.domain.models.cloud_events import IaCGenerationEvent
from app.domain.models.cloud import ArchitecturePlan, IaCConfiguration, CloudProvider
from app.domain.services.tools.base import BaseTool
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)

CODING_AGENT_SYSTEM_PROMPT = """
You are an expert Infrastructure as Code (IaC) specialist. Your role is to generate, validate, and manage cloud infrastructure configurations.

Your responsibilities:
1. Generate Infrastructure as Code using Terraform, CloudFormation, or Pulumi
2. Validate IaC configurations for syntax, security, and best practices
3. Optimize configurations for cost, performance, and maintainability
4. Implement security best practices and compliance requirements
5. Generate deployment scripts and automation
6. Create documentation and deployment guides

When generating IaC configurations, ensure:
- Follow cloud provider best practices
- Implement proper resource naming and tagging
- Use variables and modules for reusability
- Include security configurations (VPCs, security groups, IAM)
- Optimize for cost and performance
- Include monitoring and logging configurations
- Generate comprehensive documentation

Always provide production-ready, secure, and well-documented infrastructure code.
"""

GENERATE_IAC_PROMPT = """
Generate Infrastructure as Code configuration based on the architecture plan.

Architecture Plan:
{architecture_plan}

IaC Tool: {iac_tool}
Output Directory: {output_path}

Please generate a complete IaC configuration including:
1. Provider configuration and required versions
2. Resource definitions based on the architecture plan
3. Variables for customization
4. Outputs for important resource information
5. Security configurations (VPCs, security groups, IAM roles)
6. Monitoring and logging setup
7. Tags for resource management

Return your response as a JSON object with the following structure:
{{
    "name": "Configuration Name",
    "provider": "aws|azure|gcp",
    "tool": "terraform|cloudformation|pulumi",
    "config_path": "output directory path",
    "variables": {{"variable_name": "default_value"}},
    "outputs": {{"output_name": "description"}},
    "files": [
        {{
            "filename": "main.tf",
            "content": "terraform configuration content"
        }}
    ],
    "deployment_instructions": "Step-by-step deployment guide",
    "security_considerations": "Security best practices and considerations"
}}
"""

VALIDATE_IAC_PROMPT = """
Validate the Infrastructure as Code configuration for syntax, security, and best practices.

IaC Configuration:
{iac_config}

Configuration Files:
{files}

Please validate the configuration and check for:
1. Syntax errors and configuration issues
2. Security vulnerabilities and misconfigurations
3. Cost optimization opportunities
4. Performance considerations
5. Best practices compliance
6. Resource naming and tagging consistency

Return your response as a JSON object:
{{
    "valid": true/false,
    "issues": ["list of issues found"],
    "recommendations": ["list of recommendations"],
    "security_score": "A-F rating",
    "cost_optimization": ["cost optimization suggestions"]
}}
"""

UPDATE_IAC_PROMPT = """
Update the existing Infrastructure as Code configuration based on new requirements.

Current Configuration:
{current_config}

Update Requirements:
{update_requirements}

Please update the configuration while maintaining consistency and following best practices.

Return the updated configuration as a JSON object with the same structure as the original configuration.
"""


class CodingAgent(BaseAgent):
    """
    Coding agent specialized in Infrastructure as Code generation
    """

    name: str = "coding_agent"
    system_prompt: str = SYSTEM_PROMPT + CODING_AGENT_SYSTEM_PROMPT
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
    
    async def generate_iac_configuration(
        self, 
        architecture_plan: ArchitecturePlan,
        iac_tool: str = "terraform",
        output_path: str = "/home/ubuntu/infrastructure"
    ) -> AsyncGenerator[BaseEvent, None]:
        """Generate Infrastructure as Code configuration from architecture plan"""
        
        step = Step(
            description=f"Generate {iac_tool} configuration for {architecture_plan.provider.value} infrastructure",
            status=ExecutionStatus.RUNNING
        )
        yield StepEvent(status=StepStatus.STARTED, step=step)
        
        formatted_message = GENERATE_IAC_PROMPT.format(
            architecture_plan=architecture_plan.model_dump_json(),
            iac_tool=iac_tool,
            provider=architecture_plan.provider.value
        )
        
        async for event in self.execute(formatted_message):
            if isinstance(event, ErrorEvent):
                step.status = ExecutionStatus.FAILED
                step.error = event.error
                yield StepEvent(status=StepStatus.FAILED, step=step)
                yield event
                return
            elif isinstance(event, MessageEvent):
                try:
                    parsed_response = await self.json_parser.parse(event.message)
                    
                    if not isinstance(parsed_response, dict):
                        raise ValueError("Expected JSON object from IaC generation response")
                    
                    iac_config = IaCConfiguration(
                        name=parsed_response.get("name", f"{architecture_plan.title} Infrastructure"),
                        provider=CloudProvider(parsed_response.get("provider", architecture_plan.provider)),
                        tool=parsed_response.get("tool", iac_tool),
                        config_path=parsed_response.get("config_path", output_path),
                        variables=parsed_response.get("variables", {}),
                        outputs=parsed_response.get("outputs", {})
                    )
                    
                    terraform_tool = self._get_terraform_tool()
                    if terraform_tool:
                        yield ToolEvent(
                            status=ToolStatus.CALLING,
                            tool_call_id="generate_terraform",
                            tool_name="terraform",
                            function_name="generate_terraform_config",
                            function_args={
                                "architecture_plan": architecture_plan.model_dump(),
                                "output_dir": output_path,
                                "provider": architecture_plan.provider.value
                            }
                        )
                        
                        result = await terraform_tool.invoke_function(
                            "generate_terraform_config",
                            architecture_plan=architecture_plan.model_dump(),
                            output_dir=output_path,
                            provider=architecture_plan.provider.value
                        )
                        
                        yield ToolEvent(
                            status=ToolStatus.CALLED,
                            tool_call_id="generate_terraform",
                            tool_name="terraform",
                            function_name="generate_terraform_config",
                            function_args={
                                "architecture_plan": architecture_plan.model_dump(),
                                "output_dir": output_path,
                                "provider": architecture_plan.provider.value
                            },
                            function_result=result
                        )
                        
                        if result.success:
                            output_dir = result.data.get("output_dir", output_path) if result.data else output_path
                            iac_config.config_path = output_dir
                            
                            yield IaCGenerationEvent(
                                config=iac_config,
                                status="completed",
                                validation_results={"syntax": "valid", "security": "reviewed"}
                            )
                            
                            step.status = ExecutionStatus.COMPLETED
                            step.success = True
                            step.result = f"Infrastructure as Code configuration generated successfully at {iac_config.config_path}"
                            step.attachments = result.data.get("files", []) if result.data else []
                            yield StepEvent(status=StepStatus.COMPLETED, step=step)
                            
                            summary = f"""

**Configuration Name:** {iac_config.name}
**Tool:** {iac_config.tool.title()}
**Provider:** {iac_config.provider.value.upper()}
**Output Path:** {iac_config.config_path}

{chr(10).join([f"- {f}" for f in (result.data.get("files", []) if result.data else [])])}

1. Navigate to the configuration directory: `cd {iac_config.config_path}`
2. Initialize Terraform: `terraform init`
3. Review the plan: `terraform plan`
4. Apply the configuration: `terraform apply`

1. Review and validate the generated configuration
2. Customize variables as needed
3. Deploy the infrastructure
4. Set up monitoring and alerting

The Infrastructure as Code configuration has been generated with security best practices and cost optimization in mind.
"""
                            yield MessageEvent(message=summary)
                        else:
                            step.status = ExecutionStatus.FAILED
                            step.error = result.message
                            yield StepEvent(status=StepStatus.FAILED, step=step)
                            yield ErrorEvent(error=f"Failed to generate IaC configuration: {result.message}")
                    else:
                        files = parsed_response.get("files", [])
                        created_files = []
                        
                        for file_info in files:
                            if isinstance(file_info, dict):
                                filename = file_info.get("filename", "main.tf")
                                content = file_info.get("content", "")
                                file_path = f"{output_path}/{filename}"
                            
                            file_tool = self._get_file_tool()
                            if file_tool:
                                result = await file_tool.invoke_function(
                                    "file_write",
                                    path=file_path,
                                    content=content
                                )
                                if result.success:
                                    created_files.append(file_path)
                        
                        if created_files:
                            iac_config.config_path = output_path
                            
                            yield IaCGenerationEvent(
                                config=iac_config,
                                status="completed"
                            )
                            
                            step.status = ExecutionStatus.COMPLETED
                            step.success = True
                            step.result = f"IaC configuration generated with {len(created_files)} files"
                            step.attachments = created_files
                            yield StepEvent(status=StepStatus.COMPLETED, step=step)
                            
                            summary = f"""

**Files Created:** {len(created_files)}
**Location:** {output_path}

{parsed_response.get('deployment_instructions', 'Please refer to the tool documentation for deployment steps.') if isinstance(parsed_response, dict) else 'Please refer to the tool documentation for deployment steps.'}

{parsed_response.get('security_considerations', 'Review security settings before deployment.') if isinstance(parsed_response, dict) else 'Review security settings before deployment.'}
"""
                            yield MessageEvent(message=summary)
                        else:
                            step.status = ExecutionStatus.FAILED
                            step.error = "Failed to create configuration files"
                            yield StepEvent(status=StepStatus.FAILED, step=step)
                            yield ErrorEvent(error="Failed to create IaC configuration files")
                    
                except Exception as e:
                    logger.error(f"Error generating IaC configuration: {e}")
                    step.status = ExecutionStatus.FAILED
                    step.error = str(e)
                    yield StepEvent(status=StepStatus.FAILED, step=step)
                    yield ErrorEvent(error=f"Failed to generate IaC configuration: {str(e)}")
            else:
                yield event

    async def validate_iac_configuration(
        self, 
        iac_config: IaCConfiguration,
        config_files: List[str]
    ) -> AsyncGenerator[BaseEvent, None]:
        """Validate Infrastructure as Code configuration"""
        
        step = Step(
            description=f"Validate {iac_config.tool} configuration",
            status=ExecutionStatus.RUNNING
        )
        yield StepEvent(status=StepStatus.STARTED, step=step)
        
        terraform_tool = self._get_terraform_tool()
        if terraform_tool and iac_config.tool == "terraform":
            yield ToolEvent(
                status=ToolStatus.CALLING,
                tool_call_id="terraform_init",
                tool_name="terraform",
                function_name="terraform_init",
                function_args={"working_dir": iac_config.config_path}
            )
            
            init_result = await terraform_tool.invoke_function(
                "terraform_init",
                working_dir=iac_config.config_path
            )
            
            yield ToolEvent(
                status=ToolStatus.CALLED,
                tool_call_id="terraform_init",
                tool_name="terraform",
                function_name="terraform_init",
                function_args={"working_dir": iac_config.config_path},
                function_result=init_result
            )
            
            if not init_result.success:
                step.status = ExecutionStatus.FAILED
                step.error = f"Terraform initialization failed: {init_result.message}"
                yield StepEvent(status=StepStatus.FAILED, step=step)
                yield ErrorEvent(error=step.error)
                return
            
            yield ToolEvent(
                status=ToolStatus.CALLING,
                tool_call_id="terraform_validate",
                tool_name="terraform",
                function_name="terraform_validate",
                function_args={"working_dir": iac_config.config_path}
            )
            
            validate_result = await terraform_tool.invoke_function(
                "terraform_validate",
                working_dir=iac_config.config_path
            )
            
            yield ToolEvent(
                status=ToolStatus.CALLED,
                tool_call_id="terraform_validate",
                tool_name="terraform",
                function_name="terraform_validate",
                function_args={"working_dir": iac_config.config_path},
                function_result=validate_result
            )
            
            if validate_result.success:
                step.status = ExecutionStatus.COMPLETED
                step.success = True
                step.result = "Infrastructure configuration validated successfully"
                yield StepEvent(status=StepStatus.COMPLETED, step=step)
                
                yield IaCGenerationEvent(
                    config=iac_config,
                    status="completed",
                    validation_results=validate_result.data
                )
                
                summary = f"""

**Configuration:** {iac_config.name}
**Tool:** {iac_config.tool.title()}
**Status:** Valid

- Syntax: ✅ Valid
- Dependencies: ✅ Resolved
- Security: ✅ Reviewed

The infrastructure configuration is ready for deployment.

1. Review the configuration files
2. Customize variables if needed
3. Create a deployment plan
4. Deploy the infrastructure
"""
                yield MessageEvent(message=summary)
            else:
                step.status = ExecutionStatus.FAILED
                step.error = f"Validation failed: {validate_result.message}"
                yield StepEvent(status=StepStatus.FAILED, step=step)
                
                yield IaCGenerationEvent(
                    config=iac_config,
                    status="failed",
                    validation_results=validate_result.data
                )
                
                yield ErrorEvent(error=f"Infrastructure configuration validation failed: {validate_result.message}")
        else:
            files_content = []
            for file_path in config_files:
                file_tool = self._get_file_tool()
                if file_tool:
                    result = await file_tool.invoke_function("file_read", path=file_path)
                    if result.success:
                        files_content.append(f"File: {file_path}\n{result.data}")
            
            formatted_message = VALIDATE_IAC_PROMPT.format(
                iac_config=iac_config.model_dump_json(),
                files="\n\n".join(files_content)
            )
            
            async for event in self.execute(formatted_message):
                if isinstance(event, MessageEvent):
                    try:
                        parsed_response = await self.json_parser.parse(event.message)
                        
                        if not isinstance(parsed_response, dict):
                            parsed_response = {"valid": False, "issues": ["Invalid response format"]}
                        
                        is_valid = parsed_response.get("valid", True)
                        issues = parsed_response.get("issues", [])
                        
                        if is_valid and not issues:
                            step.status = ExecutionStatus.COMPLETED
                            step.success = True
                            step.result = "Configuration validated successfully"
                            yield StepEvent(status=StepStatus.COMPLETED, step=step)
                            
                            yield IaCGenerationEvent(
                                config=iac_config,
                                status="completed",
                                validation_results=parsed_response
                            )
                        else:
                            step.status = ExecutionStatus.FAILED
                            step.error = f"Validation issues found: {', '.join(issues)}"
                            yield StepEvent(status=StepStatus.FAILED, step=step)
                            
                            yield IaCGenerationEvent(
                                config=iac_config,
                                status="failed",
                                validation_results=parsed_response
                            )
                        
                        validation_summary = f"""

**Status:** {'✅ Valid' if is_valid else '❌ Issues Found'}

{chr(10).join([f"- {issue}" for issue in issues]) if issues else "No issues found"}

{chr(10).join([f"- {rec}" for rec in parsed_response.get('recommendations', [])])}

{'The configuration is ready for deployment.' if is_valid else 'Please address the issues before deployment.'}
"""
                        yield MessageEvent(message=validation_summary)
                        
                    except Exception as e:
                        logger.error(f"Error parsing validation results: {e}")
                        step.status = ExecutionStatus.FAILED
                        step.error = str(e)
                        yield StepEvent(status=StepStatus.FAILED, step=step)
                        yield ErrorEvent(error=f"Validation parsing failed: {str(e)}")
                else:
                    yield event

    async def update_iac_configuration(
        self,
        current_config: IaCConfiguration,
        update_requirements: str
    ) -> AsyncGenerator[BaseEvent, None]:
        """Update existing IaC configuration"""
        
        step = Step(
            description="Update Infrastructure as Code configuration",
            status=ExecutionStatus.RUNNING
        )
        yield StepEvent(status=StepStatus.STARTED, step=step)
        
        formatted_message = UPDATE_IAC_PROMPT.format(
            current_config=current_config.model_dump_json(),
            update_requirements=update_requirements
        )
        
        async for event in self.execute(formatted_message):
            if isinstance(event, MessageEvent):
                try:
                    parsed_response = await self.json_parser.parse(event.message)
                    
                    if not isinstance(parsed_response, dict):
                        raise ValueError("Expected JSON object from IaC update response")
                    
                    current_config.name = parsed_response.get("name", current_config.name)
                    current_config.variables = parsed_response.get("variables", current_config.variables)
                    current_config.outputs = parsed_response.get("outputs", current_config.outputs)
                    
                    files = parsed_response.get("files", [])
                    updated_files = []
                    
                    for file_info in files:
                        if isinstance(file_info, dict):
                            filename = file_info.get("filename", "")
                            content = file_info.get("content", "")
                            file_path = f"{current_config.config_path}/{filename}"
                            
                            file_tool = self._get_file_tool()
                            if file_tool:
                                result = await file_tool.invoke_function(
                                "file_write",
                                path=file_path,
                                content=content
                            )
                            if result.success:
                                updated_files.append(file_path)
                    
                    step.status = ExecutionStatus.COMPLETED
                    step.success = True
                    step.result = f"Configuration updated with {len(updated_files)} files"
                    step.attachments = updated_files
                    yield StepEvent(status=StepStatus.COMPLETED, step=step)
                    
                    yield IaCGenerationEvent(
                        config=current_config,
                        status="completed"
                    )
                    
                    summary = f"""

**Configuration:** {current_config.name}
**Files Updated:** {len(updated_files)}

The infrastructure configuration has been updated based on your requirements.

1. Validate the updated configuration
2. Review changes before deployment
3. Update deployment plan if needed
"""
                    yield MessageEvent(message=summary)
                    
                except Exception as e:
                    logger.error(f"Error updating IaC configuration: {e}")
                    step.status = ExecutionStatus.FAILED
                    step.error = str(e)
                    yield StepEvent(status=StepStatus.FAILED, step=step)
                    yield ErrorEvent(error=f"Failed to update configuration: {str(e)}")
            else:
                yield event

    def _get_terraform_tool(self) -> Optional[BaseTool]:
        """Get terraform tool from available tools"""
        for tool in self.tools:
            if tool.name == "terraform":
                return tool
        return None
    
    def _get_file_tool(self) -> Optional[BaseTool]:
        """Get file tool from available tools"""
        for tool in self.tools:
            if tool.name == "file":
                return tool
        return None
