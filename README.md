# LADS

This repository contains the LADS system (Local AI Deployment System).

Quick start diagram:

```mermaid
flowchart LR
  subgraph UserApps
    FE["Frontend (Vue/TypeScript)"]
  end

  subgraph Backend
    API["FastAPI Server"]
    Agent["Agent TaskRunner & Flows"]
    Events["Event Mapper (SSE)"]
    Repo["Session & File Repositories (MongoDB/Beanie)"]
    LLM["LLM Client (OpenAI-compatible)"]
    Search["Search Engine (Bing/Google)"]
    MCP["MCP Client"]
  end

  subgraph Sandbox
    ShellAPI["Shell API (/shell/*)"]
    FileAPI["File API (/file/*)"]
    Browser["VNC/Headless Chrome"]
    CLIs["Terraform, AWS, Azure, GCP, kubectl"]
    Mon["Prometheus/Grafana docker-compose"]
  end

  subgraph Storage
    MongoDB[(MongoDB)]
    Redis[(Redis)]
    ObjectStore[(File Storage)]
  end

  FE -- Chat/SSE --> API
  FE -- SSE events --> FE

  API -- "Create/Resume Session" --> Repo
  API -- "Stream Events (SSE)" --> FE

  API -- "Run Flow" --> Agent
  Agent -- "PlanActFlow | CloudPipelineFlow" --> Agent

  Agent -- "LLM Calls" --> LLM
  Agent -- "Search Queries" --> Search
  Agent -- "MCP Tools" --> MCP

  Agent -- "Tools: Shell/File/Browser/Message/Search\nCloud: Architecture/IaC/Terraform/K8s/Monitoring" --> Sandbox

  ShellAPI <---> Agent
  FileAPI <---> Agent
  Browser <-- CDP/VNC --> FE

  Agent -- "Persist Events/Files" --> Repo
  Repo <---> MongoDB
  Repo <---> Redis
  Repo <---> ObjectStore

  subgraph Flows
    direction TB
    PlanAct["PlanActFlow\n- PlannerAgent\n- ExecutionAgent"]
    Cloud["CloudPipelineFlow\n- ArchitecturePlannerAgent\n- IaCExecutionAgent\n- DeploymentAgent\n- MonitoringAgent"]
  end

  Agent -. uses .-> PlanAct
  Agent -. uses .-> Cloud

  subgraph EventsSSE[Events]
    MessageEvt["MessageEvent"]
    ToolEvt["ToolEvent"]
    StepEvt["StepEvent"]
    PlanEvt["PlanEvent (with mermaid, cloud state)"]
    CloudEvt["CloudPipelineEvent"]
    DoneEvt["DoneEvent"]
    WaitEvt["WaitEvent"]
  end

  Agent -- "Emit Domain Events" --> Events
  Events -- "Map to SSE" --> EventsSSE
  EventsSSE -- "Stream to Frontend" --> FE

  subgraph CloudOps[Cloud Ops via Sandbox]
    TF["terraform init/plan/apply"]
    AWSCLI["AWS CLI"]
    AZCLI["Azure CLI"]
    GCloud["Google Cloud CLI"]
    K8s["kubectl"]
    MonTools["Prometheus/Grafana Compose"]
  end

  CLIs --> TF
  CLIs --> AWSCLI
  CLIs --> AZCLI
  CLIs --> GCloud
  CLIs --> K8s
  Mon --> MonTools

  %% Pipeline: Planning -> IaC -> Deploy -> Monitor
  subgraph Pipeline[Cloud Pipeline]
    P1["Planning: ArchitecturePlan + Mermaid + Markdown (/home/ubuntu/architecture/plan.md)"]
    P2["IaC: Generate Terraform (/home/ubuntu/iac)"]
    P3["Deploy: terraform init/plan/apply"]
    P4["Monitor: Prometheus/Grafana, Health Checks, Metrics"]
  end

  Cloud -. orchestrates .-> P1 --> P2 --> P3 --> P4

  %% File sync to storage
  Agent -- "Sync created files (markdown/terraform/etc.)" --> ObjectStore
```

Run (development):

```bash
docker compose -f docker-compose-development.yml up -d
```

Run (example images):

```bash
docker compose -f docker-compose.yml up -d
```

Notes:
- Frontend at http://localhost:5173
- Backend at http://localhost:8000
- Sandbox API at http://localhost:8080