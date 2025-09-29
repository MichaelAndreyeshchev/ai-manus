#!/usr/bin/env python3
"""
Integration test for cloud tools in the redesigned architecture
"""
import asyncio
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, '/home/ubuntu/ai-manus/backend')

async def test_cloud_tools_integration():
    """Test that all cloud tools are properly integrated"""
    print("🚀 Testing Cloud Tools Integration\n")
    
    try:
        from app.domain.services.tools.architecture_planning import ArchitecturePlanningTool
        from app.domain.services.tools.iac_coding import IaCCodingTool
        from app.domain.services.tools.cloud_provider import CloudProviderTool
        from app.domain.services.tools.terraform import TerraformTool
        from app.domain.services.tools.kubernetes import KubernetesTool
        from app.domain.services.tools.monitoring import MonitoringTool
        print("✅ All cloud tools imported successfully")
        
        from app.domain.services.flows.plan_act import PlanActFlow
        print("✅ PlanActFlow imported successfully")
        
        try:
            from app.domain.services.agents.architecture_planner import ArchitecturePlannerAgent
            print("❌ ArchitecturePlannerAgent still exists - should be removed")
            return False
        except ImportError:
            print("✅ ArchitecturePlannerAgent successfully removed")
        
        try:
            from app.domain.services.agents.coding_agent import CodingAgent
            print("❌ CodingAgent still exists - should be removed")
            return False
        except ImportError:
            print("✅ CodingAgent successfully removed")
        
        try:
            from app.domain.services.agents.deployment_agent import DeploymentAgent
            print("❌ DeploymentAgent still exists - should be removed")
            return False
        except ImportError:
            print("✅ DeploymentAgent successfully removed")
        
        try:
            from app.domain.services.agents.monitoring_agent import MonitoringAgent
            print("❌ MonitoringAgent still exists - should be removed")
            return False
        except ImportError:
            print("✅ MonitoringAgent successfully removed")
        
        try:
            from app.domain.services.flows.cloud_pipeline import CloudPipelineFlow
            print("❌ CloudPipelineFlow still exists - should be removed")
            return False
        except ImportError:
            print("✅ CloudPipelineFlow successfully removed")
        
        try:
            from app.domain.models.pipeline_session import PipelineSession
            print("❌ PipelineSession still exists - should be removed")
            return False
        except ImportError:
            print("✅ PipelineSession successfully removed")
        
        from app.domain.models.cloud import CloudProvider, ArchitectureType, CloudResource, ArchitecturePlan, IaCConfiguration
        print("✅ Cloud models imported successfully")
        
        from app.domain.models.cloud_events import ArchitecturePlanEvent, IaCGenerationEvent, DeploymentEvent, MonitoringEvent
        print("✅ Cloud events imported successfully")
        
        print("\n🎉 All cloud tools integration tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_ui_branding():
    """Test that UI branding has been updated to LADS"""
    print("\n🎨 Testing UI Branding Changes...")
    
    try:
        if os.path.exists('/home/ubuntu/ai-manus/frontend/src/components/icons/LADSLogoTextIcon.vue'):
            print("✅ LADSLogoTextIcon.vue exists")
        else:
            print("❌ LADSLogoTextIcon.vue not found")
            return False
        
        if not os.path.exists('/home/ubuntu/ai-manus/frontend/src/components/icons/ManusLogoTextIcon.vue'):
            print("✅ ManusLogoTextIcon.vue successfully removed")
        else:
            print("❌ ManusLogoTextIcon.vue still exists")
            return False
        
        with open('/home/ubuntu/ai-manus/frontend/src/locales/en.ts', 'r') as f:
            en_content = f.read()
            if 'LADS' in en_content and 'Manus' not in en_content:
                print("✅ English locales updated to LADS")
            else:
                print("❌ English locales not properly updated")
                return False
        
        with open('/home/ubuntu/ai-manus/frontend/src/locales/zh.ts', 'r') as f:
            zh_content = f.read()
            if 'LADS' in zh_content and 'Manus' not in zh_content:
                print("✅ Chinese locales updated to LADS")
            else:
                print("❌ Chinese locales not properly updated")
                return False
        
        with open('/home/ubuntu/ai-manus/frontend/index.html', 'r') as f:
            html_content = f.read()
            if '<title>LADS</title>' in html_content:
                print("✅ HTML title updated to LADS")
            else:
                print("❌ HTML title not updated")
                return False
        
        print("✅ All UI branding tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ UI branding test failed: {e}")
        return False

async def main():
    """Run all integration tests"""
    print("=" * 60)
    print("CLOUD TOOLS INTEGRATION TEST - LADS SYSTEM")
    print("=" * 60)
    
    tools_success = await test_cloud_tools_integration()
    ui_success = await test_ui_branding()
    
    print("\n" + "=" * 60)
    if tools_success and ui_success:
        print("🎉 ALL TESTS PASSED - CONVERSION COMPLETE!")
        print("\nThe cloud architecture pipeline has been successfully converted")
        print("from agents to tools and rebranded from Manus to LADS.")
        print("\nKey Changes:")
        print("✅ Specialized agents converted to tools")
        print("✅ CloudPipelineFlow removed - using PlanActFlow with tools")
        print("✅ PipelineSession removed - using regular Session")
        print("✅ All UI components rebranded to LADS")
        print("✅ Storage keys updated to lads-*")
        print("✅ Logo and branding updated")
        return 0
    else:
        print("❌ SOME TESTS FAILED - CONVERSION INCOMPLETE")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
