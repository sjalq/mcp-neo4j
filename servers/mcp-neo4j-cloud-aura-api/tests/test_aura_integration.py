import os
import pytest
import logging
from mcp_neo4j_aura_manager.server import AuraAPIClient
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Skip all tests if credentials are not available
pytestmark = pytest.mark.skipif(
    not os.environ.get("NEO4J_AURA_CLIENT_ID") or not os.environ.get("NEO4J_AURA_CLIENT_SECRET"),
    reason="NEO4J_AURA_CLIENT_ID and NEO4J_AURA_CLIENT_SECRET environment variables are required for integration tests"
)

@pytest.fixture
def aura_client():
    """Create a real Aura API client using environment variables."""
    client_id = os.environ.get("NEO4J_AURA_CLIENT_ID")
    client_secret = os.environ.get("NEO4J_AURA_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        pytest.skip("NEO4J_AURA_CLIENT_ID and NEO4J_AURA_CLIENT_SECRET environment variables are required")
    
    return AuraAPIClient(client_id, client_secret)

def test_authentication(aura_client):
    """Test that authentication works with the provided credentials."""
    token = aura_client._get_auth_token()
    assert token is not None
    assert isinstance(token, str)
    assert len(token) > 0

def test_list_instances(aura_client):
    """Test listing instances from the real API."""
    instances = aura_client.list_instances()
    assert isinstance(instances, list)
    # Even if there are no instances, this should return an empty list, not fail

def test_list_tenants(aura_client):
    """Test listing tenants/projects from the real API."""
    tenants = aura_client.list_tenants()
    assert isinstance(tenants, list)
    # There should be at least one tenant if the account is valid
    assert len(tenants) > 0

def get_test_tenant(tenants):
    """Find a tenant with 'Test Tenant' in the name."""
    for tenant in tenants:
        if "Test Tenant" in tenant.get("name", ""):
            return tenant["id"]
    pytest.skip("No tenant found with 'Test Tenant' in the name")

@pytest.mark.parametrize("test_type", ["read_only", "create_instance"])
def test_integration_flow(aura_client, test_type):
    """
    Test a complete flow of operations.
    
    This test has two modes:
    - read_only: Only performs read operations
    - create_instance: Creates a test instance, updates it, then deletes it
      (WARNING: This will incur costs if run against a paid account)
    """
    # First, list all tenants
    tenants = aura_client.list_tenants()
    assert len(tenants) > 0
    tenant_id = get_test_tenant(tenants)
    
    # Get details for the first tenant
    tenant_details = aura_client.get_tenant_details(tenant_id)
    assert tenant_details["id"] == tenant_id
    assert "instance_configurations" in tenant_details
    
    # List all instances
    instances = aura_client.list_instances()
    # Verify instance details if any exist
    if instances:
        for instance in instances:
            assert "id" in instance
            assert "name" in instance
            assert "cloud_provider" in instance
            assert "created_at" in instance
            instance_details = aura_client.get_instance_details(instance["id"])
            print(instance_details)
            assert "id" in instance_details
            assert "name" in instance_details
            assert "cloud_provider" in instance_details
            assert "created_at" in instance_details
            assert "region" in instance_details
            assert "status" in instance_details
            assert "memory" in instance_details
#            assert "storage" in instance_details
#            assert "version" in instance_details
            assert "type" in instance_details
            assert isinstance(instance_details["vector_optimized"], bool)
            assert isinstance(instance_details["graph_analytics_plugin"], bool)
    
    # If we're only doing read operations, we're done
    if test_type == "read_only":
        return
    
    # WARNING: The following will create a real instance and incur costs
    # Only run this if explicitly enabled and you understand the implications
    if test_type == "create_instance" and os.environ.get("ENABLE_INSTANCE_CREATION") == "true":
        # Create a test instance
        test_instance_name = f"pytest-integration-{os.urandom(4).hex()}"
        
        try:
            # Create a small instance for testing
            instance = aura_client.create_instance(
                tenant_id=tenant_id,
                name=test_instance_name,
                memory=4,  # Minimum size
                region="us-central1",  # Use a common region
                version="5",  # Use a current version
                type="free-db",
                vector_optimized=False
            )
            
            instance_id = instance["id"]
            assert instance["name"] == test_instance_name
            
            # Update the instance name
            updated_name = f"{test_instance_name}-updated"
            updated = aura_client.update_instance(instance_id=instance_id, name=updated_name)
            assert updated["name"] == updated_name
            
            # Pause the instance
            paused = aura_client.pause_instance(instance_id)
            assert paused["status"] in ["paused", "pausing"]
            
            # Resume the instance
            resumed = aura_client.resume_instance(instance_id)
            assert resumed["status"] in ["running", "starting"]
            
            # TODO: Add code to delete the instance when done
            # This requires implementing a delete_instance method
            # which is not in the current API implementation
            
            logger.warning(
                "Test instance '%s' (ID: %s) was created but not deleted. "
                "Please delete it manually to avoid unnecessary charges.",
                test_instance_name, instance_id
            )
            
        except Exception as e:
            logger.error(f"Error during instance creation test: {str(e)}")
            raise 

def test_get_instance_details_multiple(aura_client):
    """Test getting details for multiple instances from the real API."""
    # First, list instances to get some IDs
    instances = aura_client.list_instances()
    
    # Skip if there aren't at least 2 instances
    if len(instances) < 2:
        pytest.skip("Need at least 2 instances for this test")
    
    instance_ids = [instances[0]["id"], instances[1]["id"]]
    details = aura_client.get_instance_details(instance_ids)
    
    assert isinstance(details, list)
    assert len(details) == 2
    for i, detail in enumerate(details):
        assert detail["id"] == instance_ids[i]

@pytest.mark.parametrize("test_type", ["read_only"])
def test_integration_flow_multiple(aura_client, test_type):
    """Test operations on multiple instances."""
    # First, list all instances
    instances = aura_client.list_instances()
    
    # Skip if there aren't at least 2 instances
    if len(instances) < 2:
        pytest.skip("Need at least 2 instances for this test")
    
    instance_ids = [instances[0]["id"], instances[1]["id"]]
    
    # Get details for multiple instances
    instance_details = aura_client.get_instance_details(instance_ids)
    assert isinstance(instance_details, list)
    assert len(instance_details) == 2
    
    # If we're only doing read operations, we're done
    if test_type == "read_only":
        return 

@pytest.mark.parametrize("test_type", ["create_instance"])
def test_create_instance_integration(aura_client, test_type):
    """Test creating an instance with the real API."""
    # Skip if not running the create_instance test
    if test_type != "create_instance":
        pytest.skip("Skipping instance creation test")
    
    # First, list tenants to get a tenant ID
    tenants = aura_client.list_tenants()
    assert len(tenants) > 0
    tenant_id = get_test_tenant(tenants)
    
    name = f"Test Instance {uuid.uuid4().hex[:8]}"
    # Create a test instance
    instance = aura_client.create_instance(
        tenant_id=tenant_id,
        name=name,
        memory=1,
        region="europe-west1",
        type="free-db",
        version="5",
        cloud_provider="gcp",
    )
    
    print(instance)
    assert "id" in instance
    assert "name" in instance and instance['name']==name
    assert "cloud_provider" in instance
    assert "created_at" in instance

    instance_details = aura_client.get_instance_details(instance["id"])
    print(instance_details)
    assert "id" in instance_details
    assert "name" in instance_details
    assert "cloud_provider" in instance_details
    assert "created_at" in instance_details
    assert "region" in instance_details
    assert "status" in instance_details
    assert "memory" in instance_details
#            assert "storage" in instance_details
#            assert "version" in instance_details
    assert "type" in instance_details
    assert isinstance(instance_details["vector_optimized"], bool)
    assert isinstance(instance_details["graph_analytics_plugin"], bool)

    
    # Clean up - delete the instance if possible
    # Note: This would require implementing a delete_instance method
    # which isn't shown in the original code 