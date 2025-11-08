"""Unit tests for QEOrchestrator core functionality"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from lionagi_qe.core.orchestrator import QEOrchestrator
from lionagi_qe.core.memory import QEMemory
from lionagi_qe.core.router import ModelRouter
from lionagi_qe.core.base_agent import BaseQEAgent
from lionagi_qe.core.task import QETask


class TestAgent(BaseQEAgent):
    """Test agent implementation"""
    
    def get_system_prompt(self):
        return "Test agent"
    
    async def execute(self, task):
        return {"result": "executed", "task_type": task.task_type}


@pytest.mark.unit
class TestOrchestratorInitialization:
    """Test orchestrator initialization modes"""
    
    def test_init_with_defaults(self):
        """Test initialization with all defaults"""
        orchestrator = QEOrchestrator()
        
        assert orchestrator.memory is not None
        assert orchestrator.router is not None
        assert orchestrator.enable_learning is False
        assert len(orchestrator.agents) == 0
        assert orchestrator.metrics["workflows_executed"] == 0
    
    def test_init_with_custom_memory(self):
        """Test initialization with custom memory"""
        memory = QEMemory()
        orchestrator = QEOrchestrator(memory=memory)
        
        assert orchestrator.memory is memory
        assert orchestrator.storage_config is None  # Legacy mode
    
    def test_init_with_custom_router(self):
        """Test initialization with custom router"""
        router = ModelRouter()
        orchestrator = QEOrchestrator(router=router)
        
        assert orchestrator.router is router
    
    def test_init_with_learning_enabled(self):
        """Test initialization with learning enabled"""
        orchestrator = QEOrchestrator(enable_learning=True)
        
        assert orchestrator.enable_learning is True
    
    def test_metrics_initialized(self):
        """Test all metrics initialized to zero"""
        orchestrator = QEOrchestrator()
        
        assert orchestrator.metrics["workflows_executed"] == 0
        assert orchestrator.metrics["total_agents_used"] == 0
        assert orchestrator.metrics["total_cost"] == 0.0
        assert orchestrator.metrics["parallel_expansions"] == 0
        assert orchestrator.metrics["items_processed"] == 0


@pytest.mark.unit
class TestOrchestratorAgentManagement:
    """Test agent registration and management"""
    
    def test_register_agent(self, simple_model):
        """Test registering a single agent"""
        orchestrator = QEOrchestrator()
        memory = QEMemory()
        agent = TestAgent("test-agent", simple_model, memory)
        
        orchestrator.register(agent)
        
        assert "test-agent" in orchestrator.agents
        assert orchestrator.agents["test-agent"] is agent
    
    def test_register_multiple_agents(self, simple_model):
        """Test registering multiple agents"""
        orchestrator = QEOrchestrator()
        memory = QEMemory()
        
        agent1 = TestAgent("agent-1", simple_model, memory)
        agent2 = TestAgent("agent-2", simple_model, memory)
        
        orchestrator.register(agent1)
        orchestrator.register(agent2)
        
        assert len(orchestrator.agents) == 2
        assert "agent-1" in orchestrator.agents
        assert "agent-2" in orchestrator.agents
    
    def test_register_duplicate_agent_id(self, simple_model):
        """Test registering agent with duplicate ID"""
        orchestrator = QEOrchestrator()
        memory = QEMemory()
        
        agent1 = TestAgent("duplicate", simple_model, memory)
        agent2 = TestAgent("duplicate", simple_model, memory)
        
        orchestrator.register(agent1)
        orchestrator.register(agent2)  # Should replace
        
        assert len(orchestrator.agents) == 1
        assert orchestrator.agents["duplicate"] is agent2
    
    def test_get_agent_exists(self, simple_model):
        """Test getting registered agent"""
        orchestrator = QEOrchestrator()
        memory = QEMemory()
        agent = TestAgent("test-agent", simple_model, memory)
        
        orchestrator.register(agent)
        retrieved = orchestrator.get_agent("test-agent")
        
        assert retrieved is agent
    
    def test_get_agent_not_exists(self):
        """Test getting non-existent agent returns None"""
        orchestrator = QEOrchestrator()
        
        result = orchestrator.get_agent("nonexistent")
        
        assert result is None
    
    def test_list_agents_empty(self):
        """Test listing agents when none registered"""
        orchestrator = QEOrchestrator()
        
        agents = orchestrator.list_agents()
        
        assert agents == []
    
    def test_list_agents_multiple(self, simple_model):
        """Test listing multiple agents"""
        orchestrator = QEOrchestrator()
        memory = QEMemory()
        
        agent1 = TestAgent("agent-1", simple_model, memory)
        agent2 = TestAgent("agent-2", simple_model, memory)
        
        orchestrator.register(agent1)
        orchestrator.register(agent2)
        
        agents = orchestrator.list_agents()
        
        assert len(agents) == 2
        assert "agent-1" in agents
        assert "agent-2" in agents


@pytest.mark.unit
class TestOrchestratorWorkflowExecution:
    """Test workflow execution patterns"""
    
    @pytest.mark.asyncio
    async def test_execute_single_agent(self, simple_model):
        """Test executing single agent task"""
        orchestrator = QEOrchestrator()
        memory = QEMemory()
        agent = TestAgent("test-agent", simple_model, memory)
        
        orchestrator.register(agent)
        
        task = QETask(task_type="test_task")
        result = await orchestrator.execute("test-agent", task)
        
        assert result["result"] == "executed"
        assert result["task_type"] == "test_task"
        assert orchestrator.metrics["workflows_executed"] == 1
    
    @pytest.mark.asyncio
    async def test_execute_nonexistent_agent(self):
        """Test executing task on non-existent agent"""
        orchestrator = QEOrchestrator()
        task = QETask(task_type="test_task")
        
        with pytest.raises(KeyError):
            await orchestrator.execute("nonexistent", task)
    
    @pytest.mark.asyncio
    async def test_execute_updates_metrics(self, simple_model):
        """Test execution updates metrics"""
        orchestrator = QEOrchestrator()
        memory = QEMemory()
        agent = TestAgent("test-agent", simple_model, memory)
        
        orchestrator.register(agent)
        
        initial_workflows = orchestrator.metrics["workflows_executed"]
        
        task = QETask(task_type="test_task")
        await orchestrator.execute("test-agent", task)
        
        assert orchestrator.metrics["workflows_executed"] == initial_workflows + 1


@pytest.mark.unit
class TestOrchestratorErrorHandling:
    """Test error handling scenarios"""
    
    @pytest.mark.asyncio
    async def test_execute_agent_raises_error(self, simple_model):
        """Test handling agent execution errors"""
        
        class FailingAgent(BaseQEAgent):
            def get_system_prompt(self):
                return "Failing agent"
            
            async def execute(self, task):
                raise RuntimeError("Agent execution failed")
        
        orchestrator = QEOrchestrator()
        memory = QEMemory()
        agent = FailingAgent("failing-agent", simple_model, memory)
        
        orchestrator.register(agent)
        
        task = QETask(task_type="test_task")
        
        with pytest.raises(RuntimeError, match="Agent execution failed"):
            await orchestrator.execute("failing-agent", task)
    
    def test_register_none_agent(self):
        """Test registering None as agent"""
        orchestrator = QEOrchestrator()
        
        with pytest.raises((TypeError, AttributeError)):
            orchestrator.register(None)


@pytest.mark.unit
class TestOrchestratorMetrics:
    """Test metrics tracking"""
    
    def test_get_metrics(self):
        """Test getting orchestrator metrics"""
        orchestrator = QEOrchestrator()
        orchestrator.metrics["workflows_executed"] = 5
        orchestrator.metrics["total_agents_used"] = 3
        orchestrator.metrics["total_cost"] = 2.50
        
        metrics = orchestrator.get_metrics()
        
        assert metrics["workflows_executed"] == 5
        assert metrics["total_agents_used"] == 3
        assert metrics["total_cost"] == 2.50
    
    def test_reset_metrics(self):
        """Test resetting metrics"""
        orchestrator = QEOrchestrator()
        orchestrator.metrics["workflows_executed"] = 10
        orchestrator.metrics["total_cost"] = 5.0
        
        orchestrator.reset_metrics()
        
        assert orchestrator.metrics["workflows_executed"] == 0
        assert orchestrator.metrics["total_cost"] == 0.0


@pytest.mark.unit
class TestOrchestratorSession:
    """Test session management"""
    
    def test_session_initialized(self):
        """Test session is initialized"""
        orchestrator = QEOrchestrator()
        
        assert orchestrator.session is not None
    
    def test_session_context_available(self):
        """Test session context is accessible"""
        orchestrator = QEOrchestrator()
        
        assert hasattr(orchestrator.session, 'context')
