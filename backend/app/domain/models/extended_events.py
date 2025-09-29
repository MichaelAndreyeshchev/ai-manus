from typing import Union
from app.domain.models.event import AgentEvent
from app.domain.models.cloud_events import (
    ArchitecturePlanEvent,
    IaCGenerationEvent,
    DeploymentEvent,
    MonitoringEvent,
    CloudPipelineEvent,
    CostEstimateEvent,
    CloudToolContent,
    TerraformToolContent,
    KubernetesToolContent,
    MonitoringToolContent
)

ExtendedAgentEvent = Union[
    AgentEvent,
    ArchitecturePlanEvent,
    IaCGenerationEvent,
    DeploymentEvent,
    MonitoringEvent,
    CloudPipelineEvent,
    CostEstimateEvent,
]

ExtendedToolContent = Union[
    CloudToolContent,
    TerraformToolContent,
    KubernetesToolContent,
    MonitoringToolContent
]
