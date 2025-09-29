from typing import Optional, Dict, Any, List
import json
import io
from app.domain.external.sandbox import Sandbox
from app.domain.services.tools.base import tool, BaseTool
from app.domain.models.tool_result import ToolResult
from app.domain.models.cloud import IaCConfiguration, CloudProvider

class IaCCodingTool(BaseTool):
    """Infrastructure as Code generation tool"""

    name: str = "iac_coding"
    
    def __init__(self, sandbox: Sandbox):
        super().__init__()
        self.sandbox = sandbox
        
    @tool(
        name="generate_iac_from_plan",
        description="Generate Infrastructure as Code from architecture plan",
        parameters={
            "architecture_plan": {
                "type": "object",
                "description": "Architecture plan containing resources and configuration"
            },
            "tool": {
                "type": "string",
                "description": "IaC tool to use (terraform, cloudformation, pulumi)",
                "default": "terraform"
            },
            "output_dir": {
                "type": "string",
                "description": "Directory to write IaC files",
                "default": "/home/ubuntu/iac"
            }
        },
        required=["architecture_plan"]
    )
    async def generate_iac_from_plan(
        self,
        architecture_plan: Dict[str, Any],
        tool: str = "terraform",
        output_dir: str = "/home/ubuntu/iac"
    ) -> ToolResult:
        """Generate IaC code from architecture plan"""
        try:
            provider = architecture_plan.get("provider", "aws")
            resources = architecture_plan.get("resources", [])
            
            if tool == "terraform":
                from app.domain.services.tools.terraform import TerraformTool
                terraform_tool = TerraformTool(self.sandbox)
                result = await terraform_tool.generate_terraform_config(
                    architecture_plan, output_dir, provider
                )
                
                if result.success:
                    config = IaCConfiguration(
                        name=f"{architecture_plan.get('title', 'infrastructure')}-config",
                        provider=CloudProvider(provider),
                        tool=tool,
                        config_path=output_dir,
                        variables=self._extract_variables(architecture_plan),
                        outputs=self._extract_outputs(architecture_plan)
                    )
                    
                    return ToolResult(
                        success=True,
                        message=f"IaC configuration generated successfully using {tool}",
                        data={
                            "config": config.model_dump(),
                            "files": result.data.get("files", [])
                        }
                    )
                else:
                    return result
            else:
                return ToolResult(
                    success=False,
                    message=f"Unsupported IaC tool: {tool}",
                    data={"error": f"Tool {tool} not supported"}
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error generating IaC: {str(e)}",
                data={"error": str(e)}
            )

    def _extract_variables(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Extract variables from architecture plan"""
        return {
            "region": plan.get("region", "us-east-1"),
            "environment": "production",
            "project_name": plan.get("title", "infrastructure").lower().replace(" ", "-")
        }

    def _extract_outputs(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Extract expected outputs from architecture plan"""
        outputs = {}
        resources = plan.get("resources", [])
        
        for resource in resources:
            if resource.get("type") == "compute":
                outputs[f"{resource.get('name')}_ip"] = "Instance IP address"
            elif resource.get("type") == "database":
                outputs[f"{resource.get('name')}_endpoint"] = "Database endpoint"
                
        return outputs
