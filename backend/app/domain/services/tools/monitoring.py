from typing import Optional, Dict, Any, List
import json
import time
import io
from app.domain.external.sandbox import Sandbox
from app.domain.services.tools.base import tool, BaseTool
from app.domain.models.tool_result import ToolResult
from app.domain.models.cloud import MonitoringAlert, MonitoringStatus


class MonitoringTool(BaseTool):
    """Monitoring tool for observability and alerting"""

    name: str = "monitoring"
    
    def __init__(self, sandbox: Sandbox):
        super().__init__()
        self.sandbox = sandbox
        
    @tool(
        name="setup_prometheus",
        description="Set up Prometheus monitoring",
        parameters={
            "config_dir": {
                "type": "string",
                "description": "Directory to store Prometheus configuration"
            },
            "targets": {
                "type": "array",
                "description": "List of monitoring targets",
                "items": {
                    "type": "object",
                    "properties": {
                        "job": {"type": "string"},
                        "targets": {"type": "array", "items": {"type": "string"}}
                    }
                }
            }
        },
        required=["config_dir", "targets"]
    )
    async def setup_prometheus(
        self,
        config_dir: str,
        targets: List[Dict[str, Any]]
    ) -> ToolResult:
        """Set up Prometheus monitoring"""
        try:
            mkdir_result = await self.sandbox.exec_command("mkdir", "/home/ubuntu", f"mkdir -p {config_dir}")
            if not mkdir_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to create config directory: {mkdir_result.message}",
                    data={"error": mkdir_result.message}
                )
            
            prometheus_config = self._generate_prometheus_config(targets)
            
            config_path = f"{config_dir}/prometheus.yml"
            config_data = io.BytesIO(prometheus_config.encode())
            write_result = await self.sandbox.file_upload(config_data, config_path)
            if not write_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to write Prometheus config: {write_result.message}",
                    data={"error": write_result.message}
                )
            
            docker_compose = self._generate_prometheus_docker_compose(config_dir)
            compose_path = f"{config_dir}/docker-compose.yml"
            compose_data = io.BytesIO(docker_compose.encode())
            write_result = await self.sandbox.file_upload(compose_data, compose_path)
            if not write_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to write docker-compose: {write_result.message}",
                    data={"error": write_result.message}
                )
            
            return ToolResult(
                success=True,
                message="Prometheus monitoring setup completed",
                data={
                    "config_dir": config_dir,
                    "config_file": config_path,
                    "compose_file": compose_path,
                    "targets": targets
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error setting up Prometheus: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="check_service_health",
        description="Check health of a service endpoint",
        parameters={
            "url": {
                "type": "string",
                "description": "Service health check URL"
            },
            "expected_status": {
                "type": "integer",
                "description": "Expected HTTP status code",
                "default": 200
            },
            "timeout": {
                "type": "integer",
                "description": "Request timeout in seconds",
                "default": 30
            }
        },
        required=["url"]
    )
    async def check_service_health(
        self,
        url: str,
        expected_status: int = 200,
        timeout: int = 30
    ) -> ToolResult:
        """Check service health"""
        try:
            cmd = f"curl -s -o /dev/null -w '%{{http_code}}' --max-time {timeout} {url}"
            result = await self.sandbox.exec_command("health_check", "/home/ubuntu", cmd)
            
            if result.success:
                stdout = result.data.get("stdout", "") if result.data else ""
                status_code = stdout.strip()
                try:
                    status_code = int(status_code)
                    is_healthy = status_code == expected_status
                    
                    return ToolResult(
                        success=True,
                        message=f"Service health check completed - Status: {status_code}",
                        data={
                            "url": url,
                            "status_code": status_code,
                            "expected_status": expected_status,
                            "healthy": is_healthy,
                            "status": "healthy" if is_healthy else "unhealthy"
                        }
                    )
                except ValueError:
                    return ToolResult(
                        success=False,
                        message=f"Invalid status code received: {status_code}",
                        data={"error": f"Invalid status code: {status_code}"}
                    )
            else:
                return ToolResult(
                    success=False,
                    message=f"Health check failed: {result.message}",
                    data={
                        "url": url,
                        "error": result.message,
                        "healthy": False,
                        "status": "unhealthy"
                    }
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error checking service health: {str(e)}",
                data={"error": str(e), "healthy": False, "status": "unknown"}
            )

    @tool(
        name="get_system_metrics",
        description="Get system metrics (CPU, memory, disk usage)",
        parameters={
            "host": {
                "type": "string",
                "description": "Host to check metrics for",
                "default": "localhost"
            }
        },
        required=[]
    )
    async def get_system_metrics(self, host: str = "localhost") -> ToolResult:
        """Get system metrics"""
        try:
            cpu_cmd = "top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | cut -d'%' -f1"
            cpu_result = await self.sandbox.exec_command("cpu_check", "/home/ubuntu", cpu_cmd)
            
            mem_cmd = "free | grep Mem | awk '{printf \"%.2f\", $3/$2 * 100.0}'"
            mem_result = await self.sandbox.exec_command("mem_check", "/home/ubuntu", mem_cmd)
            
            disk_cmd = "df -h / | awk 'NR==2{printf \"%s\", $5}' | cut -d'%' -f1"
            disk_result = await self.sandbox.exec_command("disk_check", "/home/ubuntu", disk_cmd)
            
            load_cmd = "uptime | awk -F'load average:' '{print $2}' | cut -d',' -f1 | xargs"
            load_result = await self.sandbox.exec_command("load_check", "/home/ubuntu", load_cmd)
            
            metrics = {}
            
            if cpu_result.success:
                try:
                    stdout = cpu_result.data.get("stdout", "0") if cpu_result.data else "0"
                    cpu_usage = float(stdout.strip())
                    metrics["cpu_usage_percent"] = cpu_usage
                except ValueError:
                    metrics["cpu_usage_percent"] = 0
            
            if mem_result.success:
                try:
                    stdout = mem_result.data.get("stdout", "0") if mem_result.data else "0"
                    mem_usage = float(stdout.strip())
                    metrics["memory_usage_percent"] = mem_usage
                except ValueError:
                    metrics["memory_usage_percent"] = 0
            
            if disk_result.success:
                try:
                    stdout = disk_result.data.get("stdout", "0") if disk_result.data else "0"
                    disk_usage = float(stdout.strip())
                    metrics["disk_usage_percent"] = disk_usage
                except ValueError:
                    metrics["disk_usage_percent"] = 0
            
            if load_result.success:
                try:
                    stdout = load_result.data.get("stdout", "0") if load_result.data else "0"
                    load_avg = float(stdout.strip())
                    metrics["load_average_1min"] = load_avg
                except ValueError:
                    metrics["load_average_1min"] = 0
            
            health_status = self._determine_health_status(metrics)
            
            return ToolResult(
                success=True,
                message="System metrics retrieved successfully",
                data={
                    "host": host,
                    "metrics": metrics,
                    "health_status": health_status,
                    "timestamp": time.time()
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error getting system metrics: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="create_alert_rule",
        description="Create monitoring alert rule",
        parameters={
            "rule_name": {
                "type": "string",
                "description": "Name of the alert rule"
            },
            "metric": {
                "type": "string",
                "description": "Metric to monitor (cpu, memory, disk, response_time)"
            },
            "threshold": {
                "type": "number",
                "description": "Alert threshold value"
            },
            "operator": {
                "type": "string",
                "description": "Comparison operator (>, <, >=, <=, ==)",
                "default": ">"
            },
            "severity": {
                "type": "string",
                "description": "Alert severity (critical, warning, info)",
                "default": "warning"
            }
        },
        required=["rule_name", "metric", "threshold"]
    )
    async def create_alert_rule(
        self,
        rule_name: str,
        metric: str,
        threshold: float,
        operator: str = ">",
        severity: str = "warning"
    ) -> ToolResult:
        """Create alert rule"""
        try:
            alert_rule = self._generate_alert_rule(rule_name, metric, threshold, operator, severity)
            
            alerts_dir = "/home/ubuntu/monitoring/alerts"
            mkdir_result = await self.sandbox.exec_command("mkdir", "/home/ubuntu", f"mkdir -p {alerts_dir}")
            if not mkdir_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to create alerts directory: {mkdir_result.message}",
                    data={"error": mkdir_result.message}
                )
            
            rule_path = f"{alerts_dir}/{rule_name}.yml"
            rule_data = io.BytesIO(alert_rule.encode())
            write_result = await self.sandbox.file_upload(rule_data, rule_path)
            if not write_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to write alert rule: {write_result.message}",
                    data={"error": write_result.message}
                )
            
            return ToolResult(
                success=True,
                message=f"Alert rule '{rule_name}' created successfully",
                data={
                    "rule_name": rule_name,
                    "rule_path": rule_path,
                    "metric": metric,
                    "threshold": threshold,
                    "operator": operator,
                    "severity": severity
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error creating alert rule: {str(e)}",
                data={"error": str(e)}
            )

    @tool(
        name="setup_grafana_dashboard",
        description="Set up Grafana dashboard for monitoring",
        parameters={
            "dashboard_name": {
                "type": "string",
                "description": "Name of the dashboard"
            },
            "metrics": {
                "type": "array",
                "description": "List of metrics to include in dashboard",
                "items": {"type": "string"}
            },
            "config_dir": {
                "type": "string",
                "description": "Directory to store Grafana configuration"
            }
        },
        required=["dashboard_name", "metrics", "config_dir"]
    )
    async def setup_grafana_dashboard(
        self,
        dashboard_name: str,
        metrics: List[str],
        config_dir: str
    ) -> ToolResult:
        """Set up Grafana dashboard"""
        try:
            mkdir_result = await self.sandbox.exec_command("mkdir", "/home/ubuntu", f"mkdir -p {config_dir}/dashboards")
            if not mkdir_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to create config directory: {mkdir_result.message}",
                    data={"error": mkdir_result.message}
                )
            
            dashboard_json = self._generate_grafana_dashboard(dashboard_name, metrics)
            
            dashboard_path = f"{config_dir}/dashboards/{dashboard_name.lower().replace(' ', '_')}.json"
            dashboard_data = io.BytesIO(dashboard_json.encode())
            write_result = await self.sandbox.file_upload(dashboard_data, dashboard_path)
            if not write_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to write dashboard: {write_result.message}",
                    data={"error": write_result.message}
                )
            
            docker_compose = self._generate_grafana_docker_compose(config_dir)
            compose_path = f"{config_dir}/docker-compose-grafana.yml"
            compose_data = io.BytesIO(docker_compose.encode())
            write_result = await self.sandbox.file_upload(compose_data, compose_path)
            if not write_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to write docker-compose: {write_result.message}",
                    data={"error": write_result.message}
                )
            
            return ToolResult(
                success=True,
                message=f"Grafana dashboard '{dashboard_name}' created successfully",
                data={
                    "dashboard_name": dashboard_name,
                    "dashboard_path": dashboard_path,
                    "compose_path": compose_path,
                    "metrics": metrics
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error setting up Grafana dashboard: {str(e)}",
                data={"error": str(e)}
            )
    
    def _generate_prometheus_config(self, targets: List[Dict[str, Any]]) -> str:
        """Generate Prometheus configuration"""
        config = {
            "global": {
                "scrape_interval": "15s",
                "evaluation_interval": "15s"
            },
            "rule_files": [
                "alerts/*.yml"
            ],
            "scrape_configs": targets
        }
        
        import yaml
        return yaml.dump(config, default_flow_style=False)
    
    def _generate_prometheus_docker_compose(self, config_dir: str) -> str:
        """Generate Prometheus docker-compose"""
        return f'''version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - {config_dir}/prometheus.yml:/etc/prometheus/prometheus.yml
      - {config_dir}/alerts:/etc/prometheus/alerts
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--web.enable-lifecycle'
    restart: unless-stopped

  alertmanager:
    image: prom/alertmanager:latest
    container_name: alertmanager
    ports:
      - "9093:9093"
    restart: unless-stopped
'''
    
    def _generate_alert_rule(self, rule_name: str, metric: str, threshold: float, operator: str, severity: str) -> str:
        """Generate Prometheus alert rule"""
        metric_mapping = {
            "cpu": "cpu_usage_percent",
            "memory": "memory_usage_percent",
            "disk": "disk_usage_percent",
            "response_time": "http_request_duration_seconds"
        }
        
        prometheus_metric = metric_mapping.get(metric, metric)
        
        rule = {
            "groups": [{
                "name": f"{rule_name}_alerts",
                "rules": [{
                    "alert": rule_name,
                    "expr": f"{prometheus_metric} {operator} {threshold}",
                    "for": "5m",
                    "labels": {
                        "severity": severity
                    },
                    "annotations": {
                        "summary": f"{rule_name} alert",
                        "description": f"{metric} is {operator} {threshold}"
                    }
                }]
            }]
        }
        
        import yaml
        return yaml.dump(rule, default_flow_style=False)
    
    def _generate_grafana_dashboard(self, dashboard_name: str, metrics: List[str]) -> str:
        """Generate Grafana dashboard JSON"""
        panels = []
        panel_id = 1
        
        for metric in metrics:
            panel = {
                "id": panel_id,
                "title": metric.replace("_", " ").title(),
                "type": "graph",
                "targets": [{
                    "expr": metric,
                    "refId": "A"
                }],
                "gridPos": {
                    "h": 8,
                    "w": 12,
                    "x": (panel_id - 1) % 2 * 12,
                    "y": ((panel_id - 1) // 2) * 8
                }
            }
            panels.append(panel)
            panel_id += 1
        
        dashboard = {
            "dashboard": {
                "id": None,
                "title": dashboard_name,
                "tags": ["monitoring"],
                "timezone": "browser",
                "panels": panels,
                "time": {
                    "from": "now-1h",
                    "to": "now"
                },
                "refresh": "5s"
            }
        }
        
        return json.dumps(dashboard, indent=2)
    
    def _generate_grafana_docker_compose(self, config_dir: str) -> str:
        """Generate Grafana docker-compose"""
        return f'''version: '3.8'

services:
  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    volumes:
      - {config_dir}/dashboards:/var/lib/grafana/dashboards
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    restart: unless-stopped
'''
    
    def _determine_health_status(self, metrics: Dict[str, float]) -> str:
        """Determine overall health status based on metrics"""
        cpu_usage = metrics.get("cpu_usage_percent", 0)
        mem_usage = metrics.get("memory_usage_percent", 0)
        disk_usage = metrics.get("disk_usage_percent", 0)
        
        if cpu_usage > 90 or mem_usage > 90 or disk_usage > 90:
            return "critical"
        elif cpu_usage > 70 or mem_usage > 70 or disk_usage > 80:
            return "warning"
        else:
            return "healthy"
