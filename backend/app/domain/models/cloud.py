from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Literal
from enum import Enum
import uuid
from datetime import datetime


class CloudProvider(str, Enum):
    """Supported cloud providers"""
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"


class ArchitectureType(str, Enum):
    """Architecture types"""
    MICROSERVICES = "microservices"
    MONOLITH = "monolith"
    SERVERLESS = "serverless"
    CONTAINER = "container"
    HYBRID = "hybrid"


class DeploymentStatus(str, Enum):
    """Deployment status"""
    PENDING = "pending"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"


class MonitoringStatus(str, Enum):
    """Monitoring status"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class CloudResource(BaseModel):
    """Cloud resource model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    type: str
    provider: CloudProvider
    region: str
    status: str
    cost_estimate: Optional[float] = None
    tags: Dict[str, str] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now())


class ArchitecturePlan(BaseModel):
    """Architecture plan model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    provider: CloudProvider
    architecture_type: ArchitectureType
    estimated_users: int
    estimated_cost_monthly: Optional[float] = None
    resources: List[CloudResource] = []
    diagram_path: Optional[str] = None
    requirements: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now())


class IaCConfiguration(BaseModel):
    """Infrastructure as Code configuration"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    provider: CloudProvider
    tool: Literal["terraform", "cloudformation", "pulumi"] = "terraform"
    config_path: str
    variables: Dict[str, Any] = {}
    outputs: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now())


class DeploymentRecord(BaseModel):
    """Deployment record"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    architecture_plan_id: str
    iac_config_id: str
    status: DeploymentStatus
    provider: CloudProvider
    region: str
    resources: List[CloudResource] = []
    deployment_logs: List[str] = []
    error_message: Optional[str] = None
    started_at: datetime = Field(default_factory=lambda: datetime.now())
    completed_at: Optional[datetime] = None


class MonitoringAlert(BaseModel):
    """Monitoring alert"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    resource_id: str
    alert_type: str
    severity: MonitoringStatus
    message: str
    threshold: Optional[float] = None
    current_value: Optional[float] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    resolved_at: Optional[datetime] = None


class MonitoringConfig(BaseModel):
    """Monitoring configuration"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    deployment_id: str
    metrics: List[str] = []
    alerts: List[MonitoringAlert] = []
    dashboards: List[str] = []
    health_check_url: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now())
