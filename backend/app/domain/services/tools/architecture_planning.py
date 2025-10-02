from typing import Optional, Dict, Any, List
import json
import io
from app.domain.external.sandbox import Sandbox
from app.domain.services.tools.base import tool, BaseTool
from app.domain.models.tool_result import ToolResult
from app.domain.models.cloud import CloudProvider, ArchitectureType, CloudResource, ArchitecturePlan

class ArchitecturePlanningTool(BaseTool):
    """Architecture planning tool for cloud infrastructure design"""

    name: str = "architecture_planning"
    
    def __init__(self, sandbox: Sandbox):
        super().__init__()
        self.sandbox = sandbox
        
    @tool(
        name="create_architecture_plan",
        description="Create a comprehensive cloud architecture plan based on requirements",
        parameters={
            "requirements": {
                "type": "object",
                "description": "User requirements including user count, budget, features, etc."
            },
            "provider": {
                "type": "string",
                "description": "Preferred cloud provider (aws, azure, gcp)",
                "default": "aws"
            },
            "architecture_type": {
                "type": "string",
                "description": "Architecture type (microservices, monolith, serverless, container, hybrid)",
                "default": "microservices"
            }
        },
        required=["requirements"]
    )
    async def create_architecture_plan(
        self,
        requirements: Dict[str, Any],
        provider: str = "aws",
        architecture_type: str = "microservices"
    ) -> ToolResult:
        """Create architecture plan from requirements"""
        try:
            estimated_users = requirements.get("users", 1000)
            budget = requirements.get("budget", 1000)
            features = requirements.get("features", [])
            
            resources = self._generate_resources(provider, architecture_type, estimated_users, features)
            estimated_cost = self._estimate_monthly_cost(resources, provider)
            
            plan = ArchitecturePlan(
                title=f"{architecture_type.title()} Architecture on {provider.upper()}",
                description=f"Scalable {architecture_type} architecture for {estimated_users:,} users",
                provider=CloudProvider(provider),
                architecture_type=ArchitectureType(architecture_type),
                estimated_users=estimated_users,
                estimated_cost_monthly=estimated_cost,
                resources=resources,
                requirements=requirements
            )
            # Generate a simple mermaid diagram string to visualize architecture
            mermaid = self._generate_mermaid_diagram(provider, architecture_type, resources)

            # Write markdown file with plan details and embedded mermaid
            md_dir = "/home/ubuntu/architecture"
            mkdir_result = await self.sandbox.exec_command("mkdir", "/home/ubuntu", f"mkdir -p {md_dir}")
            if not mkdir_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to create architecture directory: {mkdir_result.message}",
                    data={"error": mkdir_result.message}
                )

            markdown_path = f"{md_dir}/plan.md"
            md_lines = []
            md_lines.append(f"# {plan.title}")
            md_lines.append("")
            md_lines.append(plan.description)
            md_lines.append("")
            md_lines.append(f"- Provider: **{provider.upper()}**")
            md_lines.append(f"- Architecture: **{architecture_type}**")
            md_lines.append(f"- Estimated users: **{estimated_users:,}**")
            md_lines.append(f"- Estimated monthly cost: **${estimated_cost:.2f}**")
            md_lines.append("")
            md_lines.append("## Resources")
            md_lines.append("")
            md_lines.append("| Name | Type | Region | Est. Monthly Cost |")
            md_lines.append("|------|------|--------|--------------------|")
            for r in resources:
                cost = f"${r.cost_estimate:.2f}" if r.cost_estimate is not None else "-"
                md_lines.append(f"| {r.name} | {r.type} | {r.region} | {cost} |")
            md_lines.append("")
            md_lines.append("## Architecture Diagram")
            md_lines.append("")
            md_lines.append("```mermaid")
            md_lines.append(mermaid)
            md_lines.append("```")
            md_content = "\n".join(md_lines)
            md_data = io.BytesIO(md_content.encode())
            write_result = await self.sandbox.file_upload(md_data, markdown_path)
            if not write_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to write architecture markdown: {write_result.message}",
                    data={"error": write_result.message}
                )

            return ToolResult(
                success=True,
                message=f"Architecture plan created successfully for {estimated_users:,} users with estimated cost ${estimated_cost:.2f}/month",
                data={"plan": plan.model_dump(), "mermaid": mermaid, "markdown_file": markdown_path}
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error creating architecture plan: {str(e)}",
                data={"error": str(e)}
            )

    def _generate_resources(self, provider: str, arch_type: str, users: int, features: List[str]) -> List[CloudResource]:
        """Generate cloud resources based on requirements"""
        resources = []
        
        if arch_type == "microservices":
            resources.append(CloudResource(
                name="web-servers",
                type="compute",
                provider=CloudProvider(provider),
                region="us-east-1",
                status="planned",
                cost_estimate=self._get_compute_cost(users, "web")
            ))
            
            resources.append(CloudResource(
                name="api-servers",
                type="compute", 
                provider=CloudProvider(provider),
                region="us-east-1",
                status="planned",
                cost_estimate=self._get_compute_cost(users, "api")
            ))
            
            resources.append(CloudResource(
                name="database",
                type="database",
                provider=CloudProvider(provider),
                region="us-east-1", 
                status="planned",
                cost_estimate=self._get_database_cost(users)
            ))
            
            resources.append(CloudResource(
                name="load-balancer",
                type="networking",
                provider=CloudProvider(provider),
                region="us-east-1",
                status="planned",
                cost_estimate=25.0
            ))
            
        return resources

    def _get_compute_cost(self, users: int, tier: str) -> float:
        """Estimate compute costs based on user count"""
        if users < 1000:
            return 50.0 if tier == "web" else 75.0
        elif users < 10000:
            return 150.0 if tier == "web" else 200.0
        else:
            return 300.0 if tier == "web" else 400.0

    def _get_database_cost(self, users: int) -> float:
        """Estimate database costs based on user count"""
        if users < 1000:
            return 100.0
        elif users < 10000:
            return 300.0
        else:
            return 600.0

    def _estimate_monthly_cost(self, resources: List[CloudResource], provider: str) -> float:
        """Calculate total estimated monthly cost"""
        return sum(resource.cost_estimate or 0 for resource in resources)

    def _generate_mermaid_diagram(self, provider: str, arch_type: str, resources: List[CloudResource]) -> str:
        """Generate a simple mermaid flowchart for the architecture"""
        lines = ["flowchart TD"]
        # Nodes
        for res in resources:
            node = res.name.replace('-', '_')
            label = f"{res.name}\\n({res.type})"
            lines.append(f"  {node}[{label}]")
        # Basic edges for common resources
        names = [r.name.replace('-', '_') for r in resources]
        if 'load-balancer' in [r.name for r in resources] and 'web-servers' in [r.name for r in resources]:
            lines.append("  load_balancer-->web_servers")
        if 'web-servers' in [r.name for r in resources] and 'api-servers' in [r.name for r in resources]:
            lines.append("  web_servers-->api_servers")
        if 'api-servers' in [r.name for r in resources] and 'database' in [r.name for r in resources]:
            lines.append("  api_servers-->database")
        return "\n".join(lines)
