from typing import Optional, Dict, Any, List
import json
import asyncio
import io
from app.domain.external.sandbox import Sandbox
from app.domain.services.tools.base import tool, BaseTool
from app.domain.models.tool_result import ToolResult
from app.domain.models.cloud import CloudProvider, CloudResource, DeploymentStatus


class CloudProviderTool(BaseTool):
    """Cloud provider tool for AWS, Azure, GCP interactions"""

    name: str = "cloud_provider"
    
    def __init__(self, sandbox: Sandbox):
        super().__init__()
        self.sandbox = sandbox
        
    @tool(
        name="aws_configure_credentials",
        description="Configure AWS credentials for deployment operations",
        parameters={
            "access_key_id": {
                "type": "string",
                "description": "AWS access key ID"
            },
            "secret_access_key": {
                "type": "string", 
                "description": "AWS secret access key"
            },
            "region": {
                "type": "string",
                "description": "AWS region (e.g., us-east-1)"
            }
        },
        required=["access_key_id", "secret_access_key", "region"]
    )
    async def aws_configure_credentials(
        self,
        access_key_id: str,
        secret_access_key: str,
        region: str
    ) -> ToolResult:
        """Configure AWS credentials"""
        try:
            commands = [
                f"aws configure set aws_access_key_id {access_key_id}",
                f"aws configure set aws_secret_access_key {secret_access_key}",
                f"aws configure set default.region {region}",
                "aws sts get-caller-identity"
            ]
            
            results = []
            for cmd in commands:
                result = await self.sandbox.exec_command("aws_config", "/home/ubuntu", cmd)
                results.append(result.data)
                if not result.success and "get-caller-identity" not in cmd:
                    return ToolResult(
                        success=False,
                        message=f"Failed to configure AWS: {result.message}",
                        data={"error": result.message}
                    )
            
            return ToolResult(
                success=True,
                message="AWS credentials configured successfully",
                data={"results": results}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error configuring AWS credentials: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="aws_list_resources",
        description="List AWS resources in the account",
        parameters={
            "resource_type": {
                "type": "string",
                "description": "Type of resource to list (ec2, s3, rds, lambda, etc.)"
            },
            "region": {
                "type": "string",
                "description": "AWS region to query"
            }
        },
        required=["resource_type"]
    )
    async def aws_list_resources(
        self,
        resource_type: str,
        region: Optional[str] = None
    ) -> ToolResult:
        """List AWS resources"""
        try:
            region_flag = f"--region {region}" if region else ""
            
            if resource_type == "ec2":
                cmd = f"aws ec2 describe-instances {region_flag} --output json"
            elif resource_type == "s3":
                cmd = "aws s3api list-buckets --output json"
            elif resource_type == "rds":
                cmd = f"aws rds describe-db-instances {region_flag} --output json"
            elif resource_type == "lambda":
                cmd = f"aws lambda list-functions {region_flag} --output json"
            elif resource_type == "iam":
                cmd = "aws iam list-roles --output json"
            else:
                return ToolResult(
                    success=False,
                    message=f"Unsupported resource type: {resource_type}",
                    data={"error": f"Unsupported resource type: {resource_type}"}
                )
            
            result = await self.sandbox.exec_command("aws_list", "/home/ubuntu", cmd)
            
            if result.success:
                try:
                    stdout = result.data.get("stdout", "{}") if result.data else "{}"
                    data = json.loads(stdout)
                    return ToolResult(
                        success=True,
                        message=f"Successfully listed {resource_type} resources",
                        data={"resources": data}
                    )
                except json.JSONDecodeError:
                    return ToolResult(
                        success=True,
                        message=f"Listed {resource_type} resources (raw output)",
                        data={"raw_output": result.data}
                    )
            else:
                return ToolResult(
                    success=False,
                    message=f"Failed to list {resource_type} resources: {result.message}",
                    data={"error": result.message}
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error listing AWS resources: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="aws_estimate_costs",
        description="Estimate costs for AWS resources based on configuration",
        parameters={
            "resources": {
                "type": "array",
                "description": "List of resources to estimate costs for",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "instance_type": {"type": "string"},
                        "count": {"type": "integer"},
                        "region": {"type": "string"}
                    }
                }
            },
            "usage_hours": {
                "type": "integer",
                "description": "Expected usage hours per month",
                "default": 730
            }
        },
        required=["resources"]
    )
    async def aws_estimate_costs(
        self,
        resources: List[Dict[str, Any]],
        usage_hours: int = 730
    ) -> ToolResult:
        """Estimate AWS costs"""
        try:
            cost_estimates = {
                "t3.micro": 0.0104,
                "t3.small": 0.0208,
                "t3.medium": 0.0416,
                "t3.large": 0.0832,
                "m5.large": 0.096,
                "m5.xlarge": 0.192,
                "r5.large": 0.126,
                "c5.large": 0.085
            }
            
            total_cost = 0
            breakdown = {}
            
            for resource in resources:
                resource_type = resource.get("type", "")
                instance_type = resource.get("instance_type", "")
                count = resource.get("count", 1)
                
                if resource_type == "ec2" and instance_type in cost_estimates:
                    hourly_cost = cost_estimates[instance_type]
                    monthly_cost = hourly_cost * usage_hours * count
                    total_cost += monthly_cost
                    breakdown[f"{instance_type}_x{count}"] = monthly_cost
                elif resource_type == "s3":
                    monthly_cost = 0.023 * count  # $0.023 per GB
                    total_cost += monthly_cost
                    breakdown[f"s3_storage_{count}GB"] = monthly_cost
                elif resource_type == "rds":
                    monthly_cost = 0.017 * usage_hours * count
                    total_cost += monthly_cost
                    breakdown[f"rds_db.t3.micro_x{count}"] = monthly_cost
            
            return ToolResult(
                success=True,
                message=f"Estimated monthly cost: ${total_cost:.2f}",
                data={
                    "monthly_cost": round(total_cost, 2),
                    "yearly_cost": round(total_cost * 12, 2),
                    "breakdown": breakdown,
                    "currency": "USD"
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error estimating costs: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="deploy_infrastructure",
        description="Deploy infrastructure using cloud provider APIs",
        parameters={
            "iac_config": {
                "type": "object",
                "description": "Infrastructure as Code configuration"
            },
            "auto_approve": {
                "type": "boolean",
                "description": "Auto-approve deployment (use with caution)",
                "default": False
            }
        },
        required=["iac_config"]
    )
    async def deploy_infrastructure(
        self,
        iac_config: Dict[str, Any],
        auto_approve: bool = False
    ) -> ToolResult:
        """Deploy infrastructure using IaC configuration"""
        try:
            tool = iac_config.get("tool", "terraform")
            config_path = iac_config.get("config_path", "/home/ubuntu/iac")
            
            if tool == "terraform":
                from app.domain.services.tools.terraform import TerraformTool
                terraform_tool = TerraformTool(self.sandbox)
                
                init_result = await terraform_tool.terraform_init(config_path)
                if not init_result.success:
                    return init_result
                
                plan_result = await terraform_tool.terraform_plan(config_path)
                if not plan_result.success:
                    return plan_result
                
                apply_result = await terraform_tool.terraform_apply(
                    config_path, auto_approve=auto_approve
                )
                
                return ToolResult(
                    success=apply_result.success,
                    message=f"Infrastructure deployment {'completed' if apply_result.success else 'failed'}",
                    data={
                        "deployment_status": "deployed" if apply_result.success else "failed",
                        "terraform_state": apply_result.data
                    }
                )
            else:
                return ToolResult(
                    success=False,
                    message=f"Deployment tool {tool} not supported",
                    data={"error": f"Tool {tool} not supported"}
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error deploying infrastructure: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="azure_configure_credentials",
        description="Configure Azure credentials for deployment operations",
        parameters={
            "subscription_id": {
                "type": "string",
                "description": "Azure subscription ID"
            },
            "tenant_id": {
                "type": "string",
                "description": "Azure tenant ID"
            },
            "client_id": {
                "type": "string",
                "description": "Azure client ID"
            },
            "client_secret": {
                "type": "string",
                "description": "Azure client secret"
            }
        },
        required=["subscription_id", "tenant_id", "client_id", "client_secret"]
    )
    async def azure_configure_credentials(
        self,
        subscription_id: str,
        tenant_id: str,
        client_id: str,
        client_secret: str
    ) -> ToolResult:
        """Configure Azure credentials"""
        try:
            login_cmd = f"az login --service-principal -u {client_id} -p {client_secret} --tenant {tenant_id}"
            result = await self.sandbox.exec_command("azure_login", "/home/ubuntu", login_cmd)
            
            if not result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to login to Azure: {result.message}",
                    data={"error": result.message}
                )
            
            set_sub_cmd = f"az account set --subscription {subscription_id}"
            result = await self.sandbox.exec_command("azure_sub", "/home/ubuntu", set_sub_cmd)
            
            if not result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to set Azure subscription: {result.message}",
                    data={"error": result.message}
                )
            
            verify_cmd = "az account show"
            result = await self.sandbox.exec_command("azure_verify", "/home/ubuntu", verify_cmd)
            
            return ToolResult(
                success=True,
                message="Azure credentials configured successfully",
                data={"account_info": result.data}
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error configuring Azure credentials: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="gcp_configure_credentials",
        description="Configure GCP credentials for deployment operations",
        parameters={
            "service_account_key": {
                "type": "string",
                "description": "GCP service account key JSON content"
            },
            "project_id": {
                "type": "string",
                "description": "GCP project ID"
            }
        },
        required=["service_account_key", "project_id"]
    )
    async def gcp_configure_credentials(
        self,
        service_account_key: str,
        project_id: str
    ) -> ToolResult:
        """Configure GCP credentials"""
        try:
            key_path = "/home/ubuntu/gcp-key.json"
            key_data = io.BytesIO(service_account_key.encode())
            write_result = await self.sandbox.file_upload(
                key_data,
                key_path
            )
            
            if not write_result.success:
                return ToolResult(
                    success=False,
                    message="Failed to write GCP service account key",
                    data={"error": write_result.message}
                )
            
            auth_cmd = f"gcloud auth activate-service-account --key-file={key_path}"
            result = await self.sandbox.exec_command("gcp_auth", "/home/ubuntu", auth_cmd)
            
            if not result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to authenticate with GCP: {result.message}",
                    data={"error": result.message}
                )
            
            project_cmd = f"gcloud config set project {project_id}"
            result = await self.sandbox.exec_command("gcp_project", "/home/ubuntu", project_cmd)
            
            if not result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to set GCP project: {result.message}",
                    data={"error": result.message}
                )
            
            verify_cmd = "gcloud auth list"
            result = await self.sandbox.exec_command("gcp_verify", "/home/ubuntu", verify_cmd)
            
            return ToolResult(
                success=True,
                message="GCP credentials configured successfully",
                data={"auth_info": result.data}
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error configuring GCP credentials: {str(e)}",
                data={"error": str(e)}
            )
