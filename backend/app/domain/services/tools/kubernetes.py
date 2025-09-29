from typing import Optional, Dict, Any, List
import json
import yaml
import io
from app.domain.external.sandbox import Sandbox
from app.domain.services.tools.base import tool, BaseTool
from app.domain.models.tool_result import ToolResult


class KubernetesTool(BaseTool):
    """Kubernetes tool for container orchestration operations"""

    name: str = "kubernetes"
    
    def __init__(self, sandbox: Sandbox):
        super().__init__()
        self.sandbox = sandbox
        
    @tool(
        name="kubectl_apply",
        description="Apply Kubernetes configuration",
        parameters={
            "config_path": {
                "type": "string",
                "description": "Path to Kubernetes configuration file or directory"
            },
            "namespace": {
                "type": "string",
                "description": "Kubernetes namespace",
                "default": "default"
            }
        },
        required=["config_path"]
    )
    async def kubectl_apply(
        self,
        config_path: str,
        namespace: str = "default"
    ) -> ToolResult:
        """Apply Kubernetes configuration"""
        try:
            cmd = f"kubectl apply -f {config_path} -n {namespace}"
            result = await self.sandbox.exec_command("kubectl_apply", "/home/ubuntu", cmd)
            
            return ToolResult(
                success=result.success,
                message="Kubernetes configuration applied successfully" if result.success else f"kubectl apply failed: {result.message}",
                data=result.data
            )
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error applying Kubernetes configuration: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="kubectl_get",
        description="Get Kubernetes resources",
        parameters={
            "resource_type": {
                "type": "string",
                "description": "Type of resource (pods, services, deployments, etc.)"
            },
            "namespace": {
                "type": "string",
                "description": "Kubernetes namespace",
                "default": "default"
            },
            "name": {
                "type": "string",
                "description": "Specific resource name (optional)"
            }
        },
        required=["resource_type"]
    )
    async def kubectl_get(
        self,
        resource_type: str,
        namespace: str = "default",
        name: Optional[str] = None
    ) -> ToolResult:
        """Get Kubernetes resources"""
        try:
            cmd = f"kubectl get {resource_type} -n {namespace} -o json"
            if name:
                cmd = f"kubectl get {resource_type} {name} -n {namespace} -o json"
            
            result = await self.sandbox.exec_command("kubectl_get", "/home/ubuntu", cmd)
            
            if result.success:
                try:
                    stdout = result.data.get("stdout", "{}") if result.data else "{}"
                    resources = json.loads(stdout)
                    return ToolResult(
                        success=True,
                        message=f"Successfully retrieved {resource_type}",
                        data={"resources": resources}
                    )
                except json.JSONDecodeError:
                    return ToolResult(
                        success=True,
                        message=f"Retrieved {resource_type} (raw output)",
                        data=result.data
                    )
            else:
                return ToolResult(
                    success=False,
                    message=f"Failed to get {resource_type}: {result.message}",
                    data=result.data
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error getting Kubernetes resources: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="kubectl_logs",
        description="Get logs from Kubernetes pods",
        parameters={
            "pod_name": {
                "type": "string",
                "description": "Name of the pod"
            },
            "namespace": {
                "type": "string",
                "description": "Kubernetes namespace",
                "default": "default"
            },
            "container": {
                "type": "string",
                "description": "Container name (for multi-container pods)"
            },
            "tail": {
                "type": "integer",
                "description": "Number of lines to tail",
                "default": 100
            }
        },
        required=["pod_name"]
    )
    async def kubectl_logs(
        self,
        pod_name: str,
        namespace: str = "default",
        container: Optional[str] = None,
        tail: int = 100
    ) -> ToolResult:
        """Get pod logs"""
        try:
            cmd = f"kubectl logs {pod_name} -n {namespace} --tail={tail}"
            if container:
                cmd += f" -c {container}"
            
            result = await self.sandbox.exec_command("kubectl_logs", "/home/ubuntu", cmd)
            
            return ToolResult(
                success=result.success,
                message="Pod logs retrieved successfully" if result.success else f"Failed to get logs: {result.message}",
                data=result.data
            )
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error getting pod logs: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="kubectl_delete",
        description="Delete Kubernetes resources",
        parameters={
            "resource_type": {
                "type": "string",
                "description": "Type of resource (pods, services, deployments, etc.)"
            },
            "name": {
                "type": "string",
                "description": "Name of the resource to delete"
            },
            "namespace": {
                "type": "string",
                "description": "Kubernetes namespace",
                "default": "default"
            }
        },
        required=["resource_type", "name"]
    )
    async def kubectl_delete(
        self,
        resource_type: str,
        name: str,
        namespace: str = "default"
    ) -> ToolResult:
        """Delete Kubernetes resource"""
        try:
            cmd = f"kubectl delete {resource_type} {name} -n {namespace}"
            result = await self.sandbox.exec_command("kubectl_delete", "/home/ubuntu", cmd)
            
            return ToolResult(
                success=result.success,
                message=f"Resource {name} deleted successfully" if result.success else f"Failed to delete resource: {result.message}",
                data=result.data
            )
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error deleting Kubernetes resource: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="generate_k8s_manifests",
        description="Generate Kubernetes manifests from architecture plan",
        parameters={
            "architecture_plan": {
                "type": "object",
                "description": "Architecture plan containing application configuration"
            },
            "output_dir": {
                "type": "string",
                "description": "Directory to write manifest files"
            },
            "namespace": {
                "type": "string",
                "description": "Kubernetes namespace",
                "default": "default"
            }
        },
        required=["architecture_plan", "output_dir"]
    )
    async def generate_k8s_manifests(
        self,
        architecture_plan: Dict[str, Any],
        output_dir: str,
        namespace: str = "default"
    ) -> ToolResult:
        """Generate Kubernetes manifests from architecture plan"""
        try:
            mkdir_result = await self.sandbox.exec_command("mkdir", "/home/ubuntu", f"mkdir -p {output_dir}")
            if not mkdir_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to create output directory: {mkdir_result.message}",
                    data={"error": mkdir_result.message}
                )
            
            namespace_manifest = self._generate_namespace_manifest(namespace)
            
            deployments = self._generate_deployment_manifests(architecture_plan, namespace)
            
            services = self._generate_service_manifests(architecture_plan, namespace)
            
            ingress = self._generate_ingress_manifest(architecture_plan, namespace)
            
            manifests = {
                "namespace.yaml": namespace_manifest,
                "deployments.yaml": deployments,
                "services.yaml": services,
                "ingress.yaml": ingress
            }
            
            written_files = []
            for filename, content in manifests.items():
                if content:  # Only write non-empty manifests
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
                message=f"Kubernetes manifests generated successfully in {output_dir}",
                data={
                    "output_dir": output_dir,
                    "files": written_files,
                    "namespace": namespace
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error generating Kubernetes manifests: {str(e)}",
                data={"error": str(e)}
            )
    
    def _generate_namespace_manifest(self, namespace: str) -> str:
        """Generate namespace manifest"""
        if namespace == "default":
            return ""  # Don't create default namespace
        
        manifest = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": namespace
            }
        }
        return yaml.dump(manifest, default_flow_style=False)
    
    def _generate_deployment_manifests(self, architecture_plan: Dict[str, Any], namespace: str) -> str:
        """Generate deployment manifests"""
        resources = architecture_plan.get("resources", [])
        deployments = []
        
        for resource in resources:
            if resource.get("type") == "application":
                deployment = {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {
                        "name": resource.get("name", "app"),
                        "namespace": namespace
                    },
                    "spec": {
                        "replicas": resource.get("replicas", 3),
                        "selector": {
                            "matchLabels": {
                                "app": resource.get("name", "app")
                            }
                        },
                        "template": {
                            "metadata": {
                                "labels": {
                                    "app": resource.get("name", "app")
                                }
                            },
                            "spec": {
                                "containers": [{
                                    "name": resource.get("name", "app"),
                                    "image": resource.get("image", "nginx:latest"),
                                    "ports": [{
                                        "containerPort": resource.get("port", 80)
                                    }],
                                    "resources": {
                                        "requests": {
                                            "memory": resource.get("memory", "128Mi"),
                                            "cpu": resource.get("cpu", "100m")
                                        },
                                        "limits": {
                                            "memory": resource.get("memory_limit", "256Mi"),
                                            "cpu": resource.get("cpu_limit", "200m")
                                        }
                                    }
                                }]
                            }
                        }
                    }
                }
                deployments.append(deployment)
        
        if deployments:
            return yaml.dump_all(deployments, default_flow_style=False)
        return ""
    
    def _generate_service_manifests(self, architecture_plan: Dict[str, Any], namespace: str) -> str:
        """Generate service manifests"""
        resources = architecture_plan.get("resources", [])
        services = []
        
        for resource in resources:
            if resource.get("type") == "application":
                service = {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {
                        "name": f"{resource.get('name', 'app')}-service",
                        "namespace": namespace
                    },
                    "spec": {
                        "selector": {
                            "app": resource.get("name", "app")
                        },
                        "ports": [{
                            "port": resource.get("service_port", 80),
                            "targetPort": resource.get("port", 80),
                            "protocol": "TCP"
                        }],
                        "type": resource.get("service_type", "ClusterIP")
                    }
                }
                services.append(service)
        
        if services:
            return yaml.dump_all(services, default_flow_style=False)
        return ""
    
    def _generate_ingress_manifest(self, architecture_plan: Dict[str, Any], namespace: str) -> str:
        """Generate ingress manifest"""
        resources = architecture_plan.get("resources", [])
        ingress_rules = []
        
        for resource in resources:
            if resource.get("type") == "application" and resource.get("expose", False):
                rule = {
                    "host": resource.get("domain", f"{resource.get('name', 'app')}.example.com"),
                    "http": {
                        "paths": [{
                            "path": "/",
                            "pathType": "Prefix",
                            "backend": {
                                "service": {
                                    "name": f"{resource.get('name', 'app')}-service",
                                    "port": {
                                        "number": resource.get("service_port", 80)
                                    }
                                }
                            }
                        }]
                    }
                }
                ingress_rules.append(rule)
        
        if ingress_rules:
            ingress = {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "Ingress",
                "metadata": {
                    "name": "app-ingress",
                    "namespace": namespace,
                    "annotations": {
                        "nginx.ingress.kubernetes.io/rewrite-target": "/"
                    }
                },
                "spec": {
                    "rules": ingress_rules
                }
            }
            return yaml.dump(ingress, default_flow_style=False)
        return ""
