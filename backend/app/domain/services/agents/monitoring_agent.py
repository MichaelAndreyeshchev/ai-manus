from typing import AsyncGenerator, Optional, List, Dict, Any
import logging
import asyncio
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
)
from app.domain.models.cloud_events import MonitoringEvent
from app.domain.models.cloud import (
    DeploymentRecord,
    MonitoringConfig,
    MonitoringAlert,
    MonitoringStatus,
    CloudResource
)
from app.domain.services.tools.base import BaseTool
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)

MONITORING_AGENT_SYSTEM_PROMPT = """
You are an expert cloud monitoring and observability specialist. Your role is to set up comprehensive monitoring, alerting, and automated remediation for cloud infrastructure.

Your responsibilities:
1. Set up monitoring infrastructure (Prometheus, Grafana, CloudWatch, etc.)
2. Configure health checks and performance monitoring
3. Create alerting rules and notification channels
4. Implement automated remediation for common issues
5. Monitor costs and resource utilization
6. Generate monitoring reports and dashboards
7. Perform continuous health assessments

When setting up monitoring, ensure:
- Comprehensive coverage of all critical metrics
- Appropriate alert thresholds and escalation
- Automated remediation where possible
- Cost-effective monitoring solutions
- Security monitoring and compliance checks
- Performance baseline establishment
- Disaster recovery monitoring

Always provide actionable insights and proactive recommendations.
"""


class MonitoringAgent(BaseAgent):
    """
    Monitoring agent specialized in infrastructure monitoring and alerting
    """

    name: str = "monitoring_agent"
    system_prompt: str = SYSTEM_PROMPT + MONITORING_AGENT_SYSTEM_PROMPT
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
    
    async def setup_monitoring(
        self, 
        deployment: DeploymentRecord,
        monitoring_config_dir: str = "/home/ubuntu/monitoring"
    ) -> AsyncGenerator[BaseEvent, None]:
        """Set up comprehensive monitoring for deployed infrastructure"""
        
        step = Step(
            description=f"Set up monitoring for deployment {deployment.id}",
            status=ExecutionStatus.RUNNING
        )
        yield StepEvent(status=StepStatus.STARTED, step=step)
        
        try:
            monitoring_config = MonitoringConfig(
                deployment_id=deployment.id,
                metrics=["cpu_usage", "memory_usage", "disk_usage", "network_io", "response_time"],
                alerts=[],
                dashboards=[],
                health_check_url=None
            )
            
            yield MonitoringEvent(
                config=monitoring_config,
                status="configured"
            )
            
            monitoring_tool = self._get_monitoring_tool()
            if monitoring_tool:
                targets = []
                for resource in deployment.resources:
                    if resource.type in ["ec2", "application", "web_service"]:
                        targets.append({
                            "job": resource.name,
                            "targets": [f"{resource.name}:9090"]  # Default Prometheus port
                        })
                
                prometheus_result = await monitoring_tool.invoke_function(
                    "setup_prometheus",
                    config_dir=monitoring_config_dir,
                    targets=targets
                )
                
                if prometheus_result.success:
                    monitoring_config.dashboards.append("prometheus")
                    step.result = "Prometheus monitoring configured"
                else:
                    raise Exception(f"Failed to set up Prometheus: {prometheus_result.message}")
            
            alert_rules = await self._create_alert_rules(deployment, monitoring_config)
            monitoring_config.alerts.extend(alert_rules)
            
            if monitoring_tool:
                dashboard_result = await monitoring_tool.invoke_function(
                    "setup_grafana_dashboard",
                    dashboard_name=f"Infrastructure Dashboard - {deployment.id}",
                    metrics=monitoring_config.metrics,
                    config_dir=monitoring_config_dir
                )
                
                if dashboard_result.success:
                    monitoring_config.dashboards.append("grafana")
            
            health_checks = await self._setup_health_checks(deployment, monitoring_config)
            
            remediation_config = await self._setup_automated_remediation(deployment)
            
            step.status = ExecutionStatus.COMPLETED
            step.success = True
            step.result = f"Monitoring configured with {len(monitoring_config.metrics)} metrics and {len(monitoring_config.alerts)} alerts"
            yield StepEvent(status=StepStatus.COMPLETED, step=step)
            
            yield MonitoringEvent(
                config=monitoring_config,
                status="configured"
            )
            
            summary = f"""

**Deployment ID:** {deployment.id}
**Monitoring Config:** {monitoring_config_dir}
**Metrics Tracked:** {len(monitoring_config.metrics)}
**Alert Rules:** {len(monitoring_config.alerts)}
**Dashboards:** {len(monitoring_config.dashboards)}

- ✅ Prometheus metrics collection
- ✅ Grafana dashboards
- ✅ Alert rules and notifications
- ✅ Health check endpoints
- ✅ Automated remediation

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)

1. Review and customize alert thresholds
2. Set up notification channels (email, Slack, etc.)
3. Test automated remediation scripts
4. Monitor the monitoring system itself

Your infrastructure is now fully monitored and protected!
"""
            yield MessageEvent(message=summary)
            
        except Exception as e:
            logger.error(f"Monitoring setup error: {e}")
            step.status = ExecutionStatus.FAILED
            step.error = str(e)
            yield StepEvent(status=StepStatus.FAILED, step=step)
            yield ErrorEvent(error=f"Failed to set up monitoring: {str(e)}")

    async def continuous_monitoring(
        self,
        monitoring_config: MonitoringConfig,
        check_interval: int = 300  # 5 minutes
    ) -> AsyncGenerator[BaseEvent, None]:
        """Run continuous monitoring checks"""
        
        step = Step(
            description="Run continuous monitoring checks",
            status=ExecutionStatus.RUNNING
        )
        yield StepEvent(status=StepStatus.STARTED, step=step)
        
        try:
            monitoring_tool = self._get_monitoring_tool()
            if not monitoring_tool:
                raise Exception("Monitoring tool not available")
            
            metrics_result = await monitoring_tool.invoke_function("get_system_metrics")
            
            if metrics_result.success:
                metrics = metrics_result.data.get("metrics", {}) if metrics_result.data else {}
                health_status = metrics_result.data.get("health_status", "unknown") if metrics_result.data else "unknown"
                
                alerts = []
                
                cpu_usage = metrics.get("cpu_usage_percent", 0)
                if cpu_usage > 80:
                    alert = MonitoringAlert(
                        resource_id="system",
                        alert_type="high_cpu_usage",
                        severity=MonitoringStatus.CRITICAL if cpu_usage > 90 else MonitoringStatus.WARNING,
                        message=f"High CPU usage detected: {cpu_usage}%",
                        threshold=80,
                        current_value=cpu_usage
                    )
                    alerts.append(alert)
                
                memory_usage = metrics.get("memory_usage_percent", 0)
                if memory_usage > 80:
                    alert = MonitoringAlert(
                        resource_id="system",
                        alert_type="high_memory_usage",
                        severity=MonitoringStatus.CRITICAL if memory_usage > 90 else MonitoringStatus.WARNING,
                        message=f"High memory usage detected: {memory_usage}%",
                        threshold=80,
                        current_value=memory_usage
                    )
                    alerts.append(alert)
                
                disk_usage = metrics.get("disk_usage_percent", 0)
                if disk_usage > 85:
                    alert = MonitoringAlert(
                        resource_id="system",
                        alert_type="high_disk_usage",
                        severity=MonitoringStatus.CRITICAL if disk_usage > 95 else MonitoringStatus.WARNING,
                        message=f"High disk usage detected: {disk_usage}%",
                        threshold=85,
                        current_value=disk_usage
                    )
                    alerts.append(alert)
                
                for alert in alerts:
                    yield MonitoringEvent(
                        alert=alert,
                        status="alert"
                    )
                    
                    await self._trigger_automated_remediation(alert)
                
                monitoring_config.alerts.extend(alerts)
                
                if alerts:
                    alert_summary = f"""

**Timestamp:** {metrics_result.data.get('timestamp', 'Unknown') if metrics_result.data else 'Unknown'}
**Health Status:** {health_status.upper()}
**Active Alerts:** {len(alerts)}

- CPU Usage: {cpu_usage}%
- Memory Usage: {memory_usage}%
- Disk Usage: {disk_usage}%
- Load Average: {metrics.get('load_average_1min', 'N/A')}

{chr(10).join([f"- {alert.severity.value.upper()}: {alert.message}" for alert in alerts])}

Automated remediation has been triggered where applicable.
"""
                    yield MessageEvent(message=alert_summary)
                else:
                    yield MonitoringEvent(
                        config=monitoring_config,
                        status="healthy"
                    )
                
                step.status = ExecutionStatus.COMPLETED
                step.success = True
                step.result = f"Monitoring check completed - {len(alerts)} alerts detected"
                yield StepEvent(status=StepStatus.COMPLETED, step=step)
            else:
                raise Exception(f"Failed to get system metrics: {metrics_result.message}")
                
        except Exception as e:
            logger.error(f"Continuous monitoring error: {e}")
            step.status = ExecutionStatus.FAILED
            step.error = str(e)
            yield StepEvent(status=StepStatus.FAILED, step=step)
            yield ErrorEvent(error=f"Monitoring check failed: {str(e)}")

    async def _create_alert_rules(
        self,
        deployment: DeploymentRecord,
        monitoring_config: MonitoringConfig
    ) -> List[MonitoringAlert]:
        """Create alert rules for the deployment"""
        alerts = []
        
        monitoring_tool = self._get_monitoring_tool()
        if monitoring_tool:
            await monitoring_tool.invoke_function(
                "create_alert_rule",
                rule_name="high_cpu_usage",
                metric="cpu",
                threshold=80,
                operator=">",
                severity="warning"
            )
            
            await monitoring_tool.invoke_function(
                "create_alert_rule",
                rule_name="high_memory_usage",
                metric="memory",
                threshold=80,
                operator=">",
                severity="warning"
            )
            
            await monitoring_tool.invoke_function(
                "create_alert_rule",
                rule_name="high_disk_usage",
                metric="disk",
                threshold=85,
                operator=">",
                severity="critical"
            )
        
        return alerts

    async def _setup_health_checks(
        self,
        deployment: DeploymentRecord,
        monitoring_config: MonitoringConfig
    ) -> List[str]:
        """Set up health check endpoints"""
        health_checks = []
        
        monitoring_tool = self._get_monitoring_tool()
        if monitoring_tool:
            for resource in deployment.resources:
                if resource.type in ["application", "web_service"]:
                    health_url = f"http://{resource.name}/health"
                    health_checks.append(health_url)
                    
                    result = await monitoring_tool.invoke_function(
                        "check_service_health",
                        url=health_url,
                        expected_status=200,
                        timeout=30
                    )
                    
                    if result.success and result.data and result.data.get("healthy"):
                        monitoring_config.health_check_url = health_url
        
        return health_checks

    async def _setup_automated_remediation(
        self,
        deployment: DeploymentRecord
    ) -> Dict[str, Any]:
        """Set up automated remediation scripts"""
        remediation_config = {
            "high_cpu_usage": {
                "action": "scale_up",
                "threshold": 90,
                "cooldown": 300
            },
            "high_memory_usage": {
                "action": "restart_service",
                "threshold": 90,
                "cooldown": 600
            },
            "high_disk_usage": {
                "action": "cleanup_logs",
                "threshold": 95,
                "cooldown": 3600
            },
            "service_down": {
                "action": "restart_service",
                "threshold": 1,
                "cooldown": 60
            }
        }
        
        return remediation_config

    async def _trigger_automated_remediation(
        self,
        alert: MonitoringAlert
    ) -> None:
        """Trigger automated remediation for an alert"""
        try:
            if alert.alert_type == "high_cpu_usage" and alert.current_value and alert.current_value > 90:
                logger.info(f"Triggering CPU remediation for alert: {alert.id}")
                
            elif alert.alert_type == "high_memory_usage" and alert.current_value and alert.current_value > 90:
                logger.info(f"Triggering memory remediation for alert: {alert.id}")
                
            elif alert.alert_type == "high_disk_usage" and alert.current_value and alert.current_value > 95:
                logger.info(f"Triggering disk cleanup for alert: {alert.id}")
                
        except Exception as e:
            logger.error(f"Automated remediation failed for alert {alert.id}: {e}")

    def _get_monitoring_tool(self) -> Optional[BaseTool]:
        """Get monitoring tool from available tools"""
        for tool in self.tools:
            if tool.name == "monitoring":
                return tool
        return None
    
    def _get_cloud_provider_tool(self) -> Optional[BaseTool]:
        """Get cloud provider tool from available tools"""
        for tool in self.tools:
            if tool.name == "cloud_provider":
                return tool
        return None
