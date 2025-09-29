from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime
from enum import Enum
import uuid
from app.domain.models.event import BaseEvent
from app.domain.models.cloud import (
    ArchitecturePlan,
    IaCConfiguration,
    DeploymentRecord,
    MonitoringAlert,
    MonitoringConfig,
    CloudResource
)


class CloudPipelineStatus(str, Enum):
    """Cloud pipeline status"""
    PLANNING = "planning"
    CODING = "coding"
    DEPLOYING = "deploying"
    MONITORING = "monitoring"
    COMPLETED = "completed"
    FAILED = "failed"


class ArchitecturePlanEvent(BaseEvent):
    """Architecture plan event"""
    type: Literal["architecture_plan"] = "architecture_plan"
    plan: ArchitecturePlan
    status: Literal["created", "updated", "approved", "rejected"] = "created"


class IaCGenerationEvent(BaseEvent):
    """Infrastructure as Code generation event"""
    type: Literal["iac_generation"] = "iac_generation"
    config: IaCConfiguration
    status: Literal["started", "completed", "failed"] = "started"
    validation_results: Optional[Dict[str, Any]] = None


class DeploymentEvent(BaseEvent):
    """Deployment event"""
    type: Literal["deployment"] = "deployment"
    deployment: DeploymentRecord
    status: Literal["started", "in_progress", "completed", "failed", "rolling_back"] = "started"
    progress_percentage: Optional[int] = None


class MonitoringEvent(BaseEvent):
    """Monitoring event"""
    type: Literal["monitoring"] = "monitoring"
    config: Optional[MonitoringConfig] = None
    alert: Optional[MonitoringAlert] = None
    status: Literal["configured", "alert", "resolved", "healthy"] = "configured"


class CloudPipelineEvent(BaseEvent):
    """Cloud pipeline event"""
    type: Literal["cloud_pipeline"] = "cloud_pipeline"
    pipeline_status: CloudPipelineStatus
    current_stage: str
    progress_percentage: int = 0
    metadata: Dict[str, Any] = {}


class CostEstimateEvent(BaseEvent):
    """Cost estimate event"""
    type: Literal["cost_estimate"] = "cost_estimate"
    monthly_cost: float
    yearly_cost: float
    breakdown: Dict[str, float] = {}
    currency: str = "USD"


class CloudToolContent(BaseModel):
    """Cloud tool content"""
    provider: str
    operation: str
    result: Any
    resources: List[CloudResource] = []


class TerraformToolContent(BaseModel):
    """Terraform tool content"""
    operation: str
    plan_output: Optional[str] = None
    apply_output: Optional[str] = None
    state: Optional[Dict[str, Any]] = None
    resources: List[Dict[str, Any]] = []


class KubernetesToolContent(BaseModel):
    """Kubernetes tool content"""
    operation: str
    namespace: str
    resources: List[Dict[str, Any]] = []
    status: str
    logs: List[str] = []


class MonitoringToolContent(BaseModel):
    """Monitoring tool content"""
    metrics: Dict[str, Any] = {}
    alerts: List[MonitoringAlert] = []
    health_status: str = "unknown"
    uptime: Optional[float] = None
