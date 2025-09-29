from typing import Optional, Dict, Any, List
import json
import os
import io
from app.domain.external.sandbox import Sandbox
from app.domain.services.tools.base import tool, BaseTool
from app.domain.models.tool_result import ToolResult


class TerraformTool(BaseTool):
    """Terraform tool for Infrastructure as Code operations"""

    name: str = "terraform"
    
    def __init__(self, sandbox: Sandbox):
        super().__init__()
        self.sandbox = sandbox
        
    @tool(
        name="terraform_init",
        description="Initialize Terraform in a directory",
        parameters={
            "working_dir": {
                "type": "string",
                "description": "Directory containing Terraform configuration files"
            }
        },
        required=["working_dir"]
    )
    async def terraform_init(self, working_dir: str) -> ToolResult:
        """Initialize Terraform"""
        try:
            cmd = "terraform init"
            result = await self.sandbox.exec_command("terraform_init", working_dir, cmd)
            
            return ToolResult(
                success=result.success,
                message="Terraform initialized successfully" if result.success else f"Terraform init failed: {result.message}",
                data=result.data
            )
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error initializing Terraform: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="terraform_plan",
        description="Create Terraform execution plan",
        parameters={
            "working_dir": {
                "type": "string",
                "description": "Directory containing Terraform configuration files"
            },
            "var_file": {
                "type": "string",
                "description": "Path to variables file (optional)"
            },
            "variables": {
                "type": "object",
                "description": "Variables to pass to Terraform"
            }
        },
        required=["working_dir"]
    )
    async def terraform_plan(
        self,
        working_dir: str,
        var_file: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """Create Terraform plan"""
        try:
            cmd = "terraform plan -out=tfplan"
            
            if var_file:
                cmd += f" -var-file={var_file}"
            
            if variables:
                for key, value in variables.items():
                    cmd += f" -var='{key}={value}'"
            
            result = await self.sandbox.exec_command("terraform_plan", working_dir, cmd)
            
            if result.success:
                json_cmd = "terraform show -json tfplan"
                json_result = await self.sandbox.exec_command("terraform_plan_json", working_dir, json_cmd)
                
                plan_data = result.data or {}
                if json_result.success:
                    try:
                        stdout = json_result.data.get("stdout", "{}") if json_result.data else "{}"
                        plan_json = json.loads(stdout)
                        plan_data["plan_json"] = plan_json
                    except json.JSONDecodeError:
                        pass
                
                return ToolResult(
                    success=True,
                    message="Terraform plan created successfully",
                    data=plan_data
                )
            else:
                return ToolResult(
                    success=False,
                    message=f"Terraform plan failed: {result.message}",
                    data=result.data
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error creating Terraform plan: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="terraform_apply",
        description="Apply Terraform configuration",
        parameters={
            "working_dir": {
                "type": "string",
                "description": "Directory containing Terraform configuration files"
            },
            "auto_approve": {
                "type": "boolean",
                "description": "Auto-approve the apply (use with caution)",
                "default": False
            },
            "plan_file": {
                "type": "string",
                "description": "Path to plan file to apply",
                "default": "tfplan"
            }
        },
        required=["working_dir"]
    )
    async def terraform_apply(
        self,
        working_dir: str,
        auto_approve: bool = False,
        plan_file: str = "tfplan"
    ) -> ToolResult:
        """Apply Terraform configuration"""
        try:
            if auto_approve:
                cmd = f"terraform apply -auto-approve {plan_file}"
            else:
                cmd = f"terraform apply {plan_file}"
            
            result = await self.sandbox.exec_command("terraform_apply", working_dir, cmd)
            
            if result.success:
                state_cmd = "terraform show -json"
                state_result = await self.sandbox.exec_command("terraform_state", working_dir, state_cmd)
                
                apply_data = result.data or {}
                if state_result.success:
                    try:
                        stdout = state_result.data.get("stdout", "{}") if state_result.data else "{}"
                        state_json = json.loads(stdout)
                        apply_data["state"] = state_json
                    except json.JSONDecodeError:
                        pass
                
                return ToolResult(
                    success=True,
                    message="Terraform apply completed successfully",
                    data=apply_data
                )
            else:
                return ToolResult(
                    success=False,
                    message=f"Terraform apply failed: {result.message}",
                    data=result.data
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error applying Terraform: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="terraform_destroy",
        description="Destroy Terraform-managed infrastructure",
        parameters={
            "working_dir": {
                "type": "string",
                "description": "Directory containing Terraform configuration files"
            },
            "auto_approve": {
                "type": "boolean",
                "description": "Auto-approve the destroy (use with caution)",
                "default": False
            }
        },
        required=["working_dir"]
    )
    async def terraform_destroy(
        self,
        working_dir: str,
        auto_approve: bool = False
    ) -> ToolResult:
        """Destroy Terraform infrastructure"""
        try:
            if auto_approve:
                cmd = "terraform destroy -auto-approve"
            else:
                cmd = "terraform destroy"
            
            result = await self.sandbox.exec_command("terraform_destroy", working_dir, cmd)
            
            return ToolResult(
                success=result.success,
                message="Terraform destroy completed successfully" if result.success else f"Terraform destroy failed: {result.message}",
                data=result.data
            )
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error destroying Terraform infrastructure: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="terraform_validate",
        description="Validate Terraform configuration",
        parameters={
            "working_dir": {
                "type": "string",
                "description": "Directory containing Terraform configuration files"
            }
        },
        required=["working_dir"]
    )
    async def terraform_validate(self, working_dir: str) -> ToolResult:
        """Validate Terraform configuration"""
        try:
            cmd = "terraform validate -json"
            result = await self.sandbox.exec_command("terraform_validate", working_dir, cmd)
            
            if result.success:
                try:
                    stdout = result.data.get("stdout", "{}") if result.data else "{}"
                    validation_result = json.loads(stdout)
                    is_valid = validation_result.get("valid", False)
                    
                    return ToolResult(
                        success=is_valid,
                        message="Terraform configuration is valid" if is_valid else "Terraform configuration has errors",
                        data=validation_result
                    )
                except json.JSONDecodeError:
                    return ToolResult(
                        success=result.success,
                        message="Terraform validation completed",
                        data=result.data
                    )
            else:
                return ToolResult(
                    success=False,
                    message=f"Terraform validation failed: {result.message}",
                    data=result.data
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error validating Terraform: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="terraform_output",
        description="Get Terraform outputs",
        parameters={
            "working_dir": {
                "type": "string",
                "description": "Directory containing Terraform state"
            },
            "output_name": {
                "type": "string",
                "description": "Specific output to retrieve (optional)"
            }
        },
        required=["working_dir"]
    )
    async def terraform_output(
        self,
        working_dir: str,
        output_name: Optional[str] = None
    ) -> ToolResult:
        """Get Terraform outputs"""
        try:
            if output_name:
                cmd = f"terraform output -json {output_name}"
            else:
                cmd = "terraform output -json"
            
            result = await self.sandbox.exec_command("terraform_output", working_dir, cmd)
            
            if result.success:
                try:
                    stdout = result.data.get("stdout", "{}") if result.data else "{}"
                    outputs = json.loads(stdout)
                    return ToolResult(
                        success=True,
                        message="Terraform outputs retrieved successfully",
                        data={"outputs": outputs}
                    )
                except json.JSONDecodeError:
                    return ToolResult(
                        success=True,
                        message="Terraform outputs retrieved (raw)",
                        data=result.data
                    )
            else:
                return ToolResult(
                    success=False,
                    message=f"Failed to get Terraform outputs: {result.message}",
                    data=result.data
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error getting Terraform outputs: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="generate_terraform_config",
        description="Generate Terraform configuration from architecture plan",
        parameters={
            "architecture_plan": {
                "type": "object",
                "description": "Architecture plan containing resources and configuration"
            },
            "output_dir": {
                "type": "string",
                "description": "Directory to write Terraform files"
            },
            "provider": {
                "type": "string",
                "description": "Cloud provider (aws, azure, gcp)"
            }
        },
        required=["architecture_plan", "output_dir", "provider"]
    )
    async def generate_terraform_config(
        self,
        architecture_plan: Dict[str, Any],
        output_dir: str,
        provider: str
    ) -> ToolResult:
        """Generate Terraform configuration from architecture plan"""
        try:
            mkdir_result = await self.sandbox.exec_command("mkdir", "/home/ubuntu", f"mkdir -p {output_dir}")
            if not mkdir_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to create output directory: {mkdir_result.message}",
                    data={"error": mkdir_result.message}
                )
            
            provider_config = self._generate_provider_config(provider)
            
            main_config = self._generate_main_config(architecture_plan, provider)
            
            variables_config = self._generate_variables_config(architecture_plan)
            
            outputs_config = self._generate_outputs_config(architecture_plan, provider)
            
            files_to_write = {
                "provider.tf": provider_config,
                "main.tf": main_config,
                "variables.tf": variables_config,
                "outputs.tf": outputs_config
            }
            
            written_files = []
            for filename, content in files_to_write.items():
                file_path = f"{output_dir}/{filename}"
                content_data = io.BytesIO(content.encode())
                write_result = await self.sandbox.file_upload(content_data, file_path)
                if write_result.success:
                    written_files.append(file_path)
                else:
                    return ToolResult(
                        success=False,
                        message=f"Failed to write {filename}: {write_result.message}",
                        data={"error": write_result.message}
                    )
            
            return ToolResult(
                success=True,
                message=f"Terraform configuration generated successfully in {output_dir}",
                data={
                    "output_dir": output_dir,
                    "files": written_files,
                    "provider": provider
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error generating Terraform configuration: {str(e)}",
                data={"error": str(e)}
            )
    
    def _generate_provider_config(self, provider: str) -> str:
        """Generate provider configuration"""
        if provider == "aws":
            return '''terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.0"
}

provider "aws" {
  region = var.aws_region
}
'''
        elif provider == "azure":
            return '''terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
  required_version = ">= 1.0"
}

provider "azurerm" {
  features {}
}
'''
        elif provider == "gcp":
            return '''terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
  }
  required_version = ">= 1.0"
}

provider "google" {
  project = var.gcp_project
  region  = var.gcp_region
}
'''
        else:
            return "# Unsupported provider"
    
    def _generate_main_config(self, architecture_plan: Dict[str, Any], provider: str) -> str:
        """Generate main Terraform configuration"""
        resources = architecture_plan.get("resources", [])
        config_lines = []
        
        if provider == "aws":
            for resource in resources:
                resource_type = resource.get("type", "")
                if resource_type == "ec2":
                    config_lines.append(f'''
resource "aws_instance" "{resource.get('name', 'instance')}" {{
  ami           = var.ami_id
  instance_type = "{resource.get('instance_type', 't3.micro')}"
  
  tags = {{
    Name = "{resource.get('name', 'Instance')}"
  }}
}}
''')
                elif resource_type == "s3":
                    config_lines.append(f'''
resource "aws_s3_bucket" "{resource.get('name', 'bucket')}" {{
  bucket = "{resource.get('name', 'my-bucket')}"
  
  tags = {{
    Name = "{resource.get('name', 'Bucket')}"
  }}
}}
''')
        
        return "\n".join(config_lines) if config_lines else "# No resources defined"
    
    def _generate_variables_config(self, architecture_plan: Dict[str, Any]) -> str:
        """Generate variables configuration"""
        provider = architecture_plan.get("provider", "aws")
        
        if provider == "aws":
            return '''variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "ami_id" {
  description = "AMI ID for EC2 instances"
  type        = string
  default     = "ami-0c02fb55956c7d316"  # Amazon Linux 2
}
'''
        elif provider == "azure":
            return '''variable "azure_location" {
  description = "Azure location"
  type        = string
  default     = "East US"
}

variable "resource_group_name" {
  description = "Resource group name"
  type        = string
  default     = "rg-main"
}
'''
        elif provider == "gcp":
            return '''variable "gcp_project" {
  description = "GCP project ID"
  type        = string
}

variable "gcp_region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}
'''
        else:
            return "# No variables defined"
    
    def _generate_outputs_config(self, architecture_plan: Dict[str, Any], provider: str) -> str:
        """Generate outputs configuration"""
        resources = architecture_plan.get("resources", [])
        output_lines = []
        
        if provider == "aws":
            for resource in resources:
                if resource.get("type") == "ec2":
                    name = resource.get("name", "instance")
                    output_lines.append(f'''
output "{name}_public_ip" {{
  description = "Public IP of {name}"
  value       = aws_instance.{name}.public_ip
}}

output "{name}_private_ip" {{
  description = "Private IP of {name}"
  value       = aws_instance.{name}.private_ip
}}
''')
        
        return "\n".join(output_lines) if output_lines else "# No outputs defined"
