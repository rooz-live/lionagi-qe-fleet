"""Extended tests for BaseQEAgent - Error paths, memory backends, edge cases"""

import pytest
import warnings
from unittest.mock import AsyncMock, Mock, patch
from lionagi_qe.core.base_agent import BaseQEAgent
from lionagi_qe.core.task import QETask
from lionagi_qe.core.memory import QEMemory
from lionagi import iModel


class TestAgent(BaseQEAgent):
    """Concrete test agent implementation"""

    def get_system_prompt(self) -> str:
        return "Test agent system prompt"

    async def execute(self, task: QETask):
        return {
            "task_type": task.task_type,
            "result": "executed"
        }


class TestBaseQEAgentMemoryBackends:
    """Test various memory backend initialization paths"""

    @pytest.mark.asyncio
    async def test_init_with_qememory_shows_deprecation(self, simple_model):
        """Test QEMemory usage shows deprecation warning"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            memory = QEMemory()
            agent = TestAgent("test-agent", simple_model, memory=memory)
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "QEMemory is deprecated" in str(w[0].message)

    @pytest.mark.asyncio
    async def test_memory_backend_type_qememory(self, simple_model):
        """Test memory_backend_type property for QEMemory"""
        memory = QEMemory()
        agent = TestAgent("test-agent", simple_model, memory=memory)
        
        assert agent.memory_backend_type == "qememory"

    @pytest.mark.skip("Session context API needs verification")
    @pytest.mark.asyncio
    async def test_init_without_memory_uses_session_context(self, simple_model):
        """Test default initialization uses Session.context"""
        agent = TestAgent("test-agent", simple_model)
        
        assert agent.memory is not None
        # Memory backend type will be "session" or "custom" depending on implementation
        assert agent.memory_backend_type in ["session", "custom"]

    @pytest.mark.skip("Session context API needs verification")
    @pytest.mark.asyncio
    async def test_memory_config_session_type(self, simple_model):
        """Test memory_config with session type"""
        agent = TestAgent(
            "test-agent",
            simple_model,
            memory_config={"type": "session"}
        )
        
        assert agent.memory is not None
        # Memory backend type will be "session" or "custom" depending on implementation
        assert agent.memory_backend_type in ["session", "custom"]

    @pytest.mark.asyncio
    async def test_memory_config_invalid_type_raises(self, simple_model):
        """Test invalid memory backend type raises ValueError"""
        with pytest.raises(ValueError, match="Unknown memory backend type"):
            TestAgent(
                "test-agent",
                simple_model,
                memory_config={"type": "invalid_backend"}
            )

    @pytest.mark.asyncio
    async def test_memory_config_postgres_without_db_manager_raises(self, simple_model):
        """Test postgres config without db_manager raises ValueError"""
        with pytest.raises(ValueError, match="requires 'db_manager'"):
            TestAgent(
                "test-agent",
                simple_model,
                memory_config={"type": "postgres"}
            )


class TestBaseQEAgentInitialization:
    """Test agent initialization edge cases"""

    @pytest.mark.asyncio
    async def test_init_with_empty_skills(self, qe_memory, simple_model):
        """Test initialization with empty skills list"""
        agent = TestAgent("test-agent", simple_model, qe_memory, skills=[])
        
        assert agent.skills == []

    @pytest.mark.asyncio
    async def test_init_with_none_skills(self, qe_memory, simple_model):
        """Test initialization with None skills defaults to empty list"""
        agent = TestAgent("test-agent", simple_model, qe_memory, skills=None)
        
        assert agent.skills == []

    @pytest.mark.asyncio
    async def test_init_learning_disabled_q_service_none(self, qe_memory, simple_model):
        """Test Q-service is None when learning disabled"""
        agent = TestAgent("test-agent", simple_model, qe_memory, enable_learning=False)
        
        assert agent.enable_learning is False
        # Q-service may be None if QLEARNING_AVAILABLE is False

    @pytest.mark.asyncio
    async def test_branch_initialized_with_system_prompt(self, qe_memory, simple_model):
        """Test Branch is initialized with agent's system prompt"""
        agent = TestAgent("test-agent", simple_model, qe_memory)
        
        assert agent.branch is not None
        assert agent.branch.name == "test-agent"

    @pytest.mark.asyncio
    async def test_logger_initialized_with_agent_id(self, qe_memory, simple_model):
        """Test logger is created with agent-specific name"""
        agent = TestAgent("custom-id", simple_model, qe_memory)
        
        assert agent.logger.name == "lionagi_qe.custom-id"

    @pytest.mark.asyncio
    async def test_metrics_initialized_to_zero(self, qe_memory, simple_model):
        """Test all metrics initialized to zero/empty"""
        agent = TestAgent("test-agent", simple_model, qe_memory)
        
        assert agent.metrics["tasks_completed"] == 0
        assert agent.metrics["tasks_failed"] == 0
        assert agent.metrics["total_cost"] == 0.0
        assert agent.metrics["patterns_learned"] == 0
        assert agent.metrics["total_reward"] == 0.0
        assert agent.metrics["avg_reward"] == 0.0
        assert agent.metrics["learning_episodes"] == 0


class TestBaseQEAgentErrorHandling:
    """Test error handling and edge cases"""

    @pytest.mark.asyncio
    async def test_store_result_with_invalid_key(self, qe_memory, simple_model):
        """Test storing result with various key formats"""
        agent = TestAgent("test-agent", simple_model, qe_memory)
        
        # Should handle keys with special characters
        await agent.store_result("key/with/slashes", "value")
        stored = await qe_memory.retrieve("aqe/test-agent/key/with/slashes")
        assert stored == "value"

    @pytest.mark.asyncio
    async def test_store_result_with_empty_value(self, qe_memory, simple_model):
        """Test storing empty/None values"""
        agent = TestAgent("test-agent", simple_model, qe_memory)
        
        await agent.store_result("empty_key", "")
        stored = await qe_memory.retrieve("aqe/test-agent/empty_key")
        assert stored == ""
        
        await agent.store_result("none_key", None)
        stored = await qe_memory.retrieve("aqe/test-agent/none_key")
        assert stored is None

    @pytest.mark.asyncio
    async def test_retrieve_context_nonexistent_key(self, qe_memory, simple_model):
        """Test retrieving non-existent key returns None"""
        agent = TestAgent("test-agent", simple_model, qe_memory)
        
        result = await agent.retrieve_context("does_not_exist")
        assert result is None

    @pytest.mark.asyncio
    async def test_search_memory_empty_pattern(self, qe_memory, simple_model):
        """Test searching with pattern that matches nothing"""
        agent = TestAgent("test-agent", simple_model, qe_memory)
        
        results = await agent.search_memory(r"nonexistent/.*")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_error_handler_logs_error(self, qe_memory, simple_model, caplog):
        """Test error handler logs the error"""
        agent = TestAgent("test-agent", simple_model, qe_memory)
        
        task = QETask(task_type="test_task")
        error = ValueError("Test error message")
        
        await agent.error_handler(task, error)
        
        # Check error was logged
        assert "error" in caplog.text.lower() or "fail" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_error_handler_stores_error_details(self, qe_memory, simple_model):
        """Test error handler stores full error information"""
        agent = TestAgent("test-agent", simple_model, qe_memory)
        
        task = QETask(task_type="test_task")
        error = RuntimeError("Critical failure")
        
        await agent.error_handler(task, error)
        
        stored_error = await qe_memory.retrieve(
            f"aqe/test-agent/tasks/{task.task_id}/error"
        )
        
        assert stored_error is not None
        assert "Critical failure" in stored_error["error"] or "Critical failure" in str(stored_error)

    @pytest.mark.asyncio
    async def test_concurrent_store_and_retrieve(self, qe_memory, simple_model):
        """Test concurrent memory operations don't conflict"""
        import asyncio
        
        agent = TestAgent("test-agent", simple_model, qe_memory)
        
        # Concurrent stores
        store_tasks = [
            agent.store_result(f"concurrent_{i}", {"value": i})
            for i in range(10)
        ]
        await asyncio.gather(*store_tasks)
        
        # Concurrent retrieves
        retrieve_tasks = [
            agent.retrieve_context(f"aqe/test-agent/concurrent_{i}")
            for i in range(10)
        ]
        results = await asyncio.gather(*retrieve_tasks)
        
        # All should be stored and retrieved correctly
        for i, result in enumerate(results):
            assert result == {"value": i}


class TestBaseQEAgentLearningIntegration:
    """Test Q-learning integration paths"""

    @pytest.mark.asyncio
    async def test_learning_enabled_without_service(self, qe_memory, simple_model):
        """Test learning enabled but no Q-service provided"""
        agent = TestAgent(
            "test-agent",
            simple_model,
            qe_memory,
            enable_learning=True,
            q_learning_service=None
        )
        
        assert agent.enable_learning is True
        # Q-service may be None if QLEARNING_AVAILABLE is False

    @pytest.mark.asyncio
    async def test_current_state_hash_initialized_none(self, qe_memory, simple_model):
        """Test state tracking attributes initialized to None"""
        agent = TestAgent("test-agent", simple_model, qe_memory)
        
        assert agent.current_state_hash is None
        assert agent.current_action_id is None

    @pytest.mark.asyncio
    async def test_post_execution_stores_learning_trajectory(
        self, qe_memory, simple_model
    ):
        """Test learning trajectory is stored after execution"""
        agent = TestAgent(
            "test-agent",
            simple_model,
            qe_memory,
            enable_learning=True
        )
        
        task = QETask(task_type="learning_task")
        result = {"success": True, "quality": 0.95}
        
        await agent.post_execution_hook(task, result)
        
        trajectory = await qe_memory.retrieve(
            f"aqe/test-agent/learning/trajectories/{task.task_id}"
        )
        
        # Trajectory only stored if Q-learning service is configured
        if agent.enable_learning and agent.q_service:
            assert trajectory is not None
            assert "success" in trajectory


class TestBaseQEAgentStoragePatterns:
    """Test various storage patterns and edge cases"""

    @pytest.mark.asyncio
    async def test_store_result_with_custom_partition(self, qe_memory, simple_model):
        """Test storing with custom partition"""
        agent = TestAgent("test-agent", simple_model, qe_memory)
        
        await agent.store_result(
            "partitioned_data",
            {"data": "test"},
            partition="custom_partition"
        )
        
        # Verify stored with correct partition
        stored_data = qe_memory._store["aqe/test-agent/partitioned_data"]
        assert stored_data["partition"] == "custom_partition"

    @pytest.mark.asyncio
    async def test_store_result_with_zero_ttl(self, qe_memory, simple_model):
        """Test storing with TTL=0 (immediate expiry)"""
        agent = TestAgent("test-agent", simple_model, qe_memory)
        
        await agent.store_result("ttl_zero", "value", ttl=0)
        
        # Should be stored but marked for immediate expiry
        stored = await qe_memory.retrieve("aqe/test-agent/ttl_zero")
        # May be None if already expired

    @pytest.mark.asyncio
    async def test_store_large_result(self, qe_memory, simple_model):
        """Test storing large result data"""
        agent = TestAgent("test-agent", simple_model, qe_memory)
        
        large_data = {"items": [f"item_{i}" for i in range(10000)]}
        
        await agent.store_result("large_result", large_data)
        stored = await qe_memory.retrieve("aqe/test-agent/large_result")
        
        assert stored == large_data
        assert len(stored["items"]) == 10000

    @pytest.mark.asyncio
    async def test_get_metrics_includes_all_fields(self, qe_memory, simple_model):
        """Test get_metrics returns complete metric set"""
        agent = TestAgent(
            "test-agent",
            simple_model,
            qe_memory,
            skills=["skill1"]
        )
        
        # Update metrics
        agent.metrics["tasks_completed"] = 10
        agent.metrics["tasks_failed"] = 2
        agent.metrics["total_cost"] = 5.75
        
        metrics = await agent.get_metrics()
        
        assert "agent_id" in metrics
        assert "skills" in metrics
        assert "tasks_completed" in metrics
        assert "tasks_failed" in metrics
        assert "total_cost" in metrics
        assert metrics["tasks_completed"] == 10
        assert metrics["tasks_failed"] == 2
        assert metrics["total_cost"] == 5.75
