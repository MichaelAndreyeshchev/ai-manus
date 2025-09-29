from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.domain.models.session import Session
from app.domain.models.cloud import (
    ArchitecturePlan,
    IaCConfiguration,
    DeploymentRecord,
    MonitoringConfig
)
from app.domain.models.cloud_events import CloudPipelineStatus


class PipelineSession(Session):
    """
    Extended session model for cloud pipeline workflows
    """
    
    pipeline_stage: str = "planning"  # planning, coding, deployment, monitoring, completed
    pipeline_status: CloudPipelineStatus = CloudPipelineStatus.PLANNING
    
    architecture_plan_id: Optional[str] = None
    architecture_plan: Optional[ArchitecturePlan] = None
    
    iac_config_id: Optional[str] = None
    iac_config: Optional[IaCConfiguration] = None
    
    deployment_id: Optional[str] = None
    deployment: Optional[DeploymentRecord] = None
    
    monitoring_config_id: Optional[str] = None
    monitoring_config: Optional[MonitoringConfig] = None
    
    user_requirements: Dict[str, Any] = {}
    pipeline_progress: int = 0  # 0-100
    pipeline_metadata: Dict[str, Any] = {}
    
    planning_started_at: Optional[datetime] = None
    planning_completed_at: Optional[datetime] = None
    coding_started_at: Optional[datetime] = None
    coding_completed_at: Optional[datetime] = None
    deployment_started_at: Optional[datetime] = None
    deployment_completed_at: Optional[datetime] = None
    monitoring_started_at: Optional[datetime] = None
    monitoring_completed_at: Optional[datetime] = None
    
    def start_planning_stage(self) -> None:
        """Start the planning stage"""
        self.pipeline_stage = "planning"
        self.pipeline_status = CloudPipelineStatus.PLANNING
        self.planning_started_at = datetime.now()
        self.pipeline_progress = 0
    
    def complete_planning_stage(self, architecture_plan: ArchitecturePlan) -> None:
        """Complete the planning stage"""
        self.architecture_plan = architecture_plan
        self.architecture_plan_id = architecture_plan.id
        self.planning_completed_at = datetime.now()
        self.pipeline_progress = 25
    
    def start_coding_stage(self) -> None:
        """Start the coding stage"""
        self.pipeline_stage = "coding"
        self.pipeline_status = CloudPipelineStatus.CODING
        self.coding_started_at = datetime.now()
    
    def complete_coding_stage(self, iac_config: IaCConfiguration) -> None:
        """Complete the coding stage"""
        self.iac_config = iac_config
        self.iac_config_id = iac_config.id
        self.coding_completed_at = datetime.now()
        self.pipeline_progress = 50
    
    def start_deployment_stage(self) -> None:
        """Start the deployment stage"""
        self.pipeline_stage = "deployment"
        self.pipeline_status = CloudPipelineStatus.DEPLOYING
        self.deployment_started_at = datetime.now()
    
    def complete_deployment_stage(self, deployment: DeploymentRecord) -> None:
        """Complete the deployment stage"""
        self.deployment = deployment
        self.deployment_id = deployment.id
        self.deployment_completed_at = datetime.now()
        self.pipeline_progress = 75
    
    def start_monitoring_stage(self) -> None:
        """Start the monitoring stage"""
        self.pipeline_stage = "monitoring"
        self.pipeline_status = CloudPipelineStatus.MONITORING
        self.monitoring_started_at = datetime.now()
    
    def complete_monitoring_stage(self, monitoring_config: MonitoringConfig) -> None:
        """Complete the monitoring stage"""
        self.monitoring_config = monitoring_config
        self.monitoring_config_id = monitoring_config.id
        self.monitoring_completed_at = datetime.now()
        self.pipeline_progress = 100
    
    def complete_pipeline(self) -> None:
        """Mark the entire pipeline as completed"""
        self.pipeline_stage = "completed"
        self.pipeline_status = CloudPipelineStatus.COMPLETED
        self.pipeline_progress = 100
    
    def fail_pipeline(self, error_message: str) -> None:
        """Mark the pipeline as failed"""
        self.pipeline_status = CloudPipelineStatus.FAILED
        self.pipeline_metadata["error"] = error_message
        self.pipeline_metadata["failed_at"] = datetime.now().isoformat()
    
    def get_pipeline_duration(self) -> Optional[float]:
        """Get total pipeline duration in seconds"""
        if self.planning_started_at and self.monitoring_completed_at:
            return (self.monitoring_completed_at - self.planning_started_at).total_seconds()
        return None
    
    def get_stage_duration(self, stage: str) -> Optional[float]:
        """Get duration of a specific stage in seconds"""
        if stage == "planning" and self.planning_started_at and self.planning_completed_at:
            return (self.planning_completed_at - self.planning_started_at).total_seconds()
        elif stage == "coding" and self.coding_started_at and self.coding_completed_at:
            return (self.coding_completed_at - self.coding_started_at).total_seconds()
        elif stage == "deployment" and self.deployment_started_at and self.deployment_completed_at:
            return (self.deployment_completed_at - self.deployment_started_at).total_seconds()
        elif stage == "monitoring" and self.monitoring_started_at and self.monitoring_completed_at:
            return (self.monitoring_completed_at - self.monitoring_started_at).total_seconds()
        return None
    
    def get_pipeline_summary(self) -> Dict[str, Any]:
        """Get a summary of the pipeline execution"""
        return {
            "pipeline_id": self.id,
            "status": self.pipeline_status.value,
            "stage": self.pipeline_stage,
            "progress": self.pipeline_progress,
            "duration": self.get_pipeline_duration(),
            "stages": {
                "planning": {
                    "duration": self.get_stage_duration("planning"),
                    "completed": self.planning_completed_at is not None,
                    "artifact": self.architecture_plan_id
                },
                "coding": {
                    "duration": self.get_stage_duration("coding"),
                    "completed": self.coding_completed_at is not None,
                    "artifact": self.iac_config_id
                },
                "deployment": {
                    "duration": self.get_stage_duration("deployment"),
                    "completed": self.deployment_completed_at is not None,
                    "artifact": self.deployment_id
                },
                "monitoring": {
                    "duration": self.get_stage_duration("monitoring"),
                    "completed": self.monitoring_completed_at is not None,
                    "artifact": self.monitoring_config_id
                }
            },
            "resources_deployed": len(self.deployment.resources) if self.deployment else 0,
            "estimated_cost": self.architecture_plan.estimated_cost_monthly if self.architecture_plan else None,
            "provider": self.architecture_plan.provider.value if self.architecture_plan else None,
            "architecture_type": self.architecture_plan.architecture_type.value if self.architecture_plan else None
        }
