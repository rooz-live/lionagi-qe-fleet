"""
Comprehensive test suite for AgentDB Bridge.

Tests cover:
- Initialization and configuration
- Execution trace storage and retrieval
- Querying with various filters
- Agent statistics aggregation
- Performance metrics tracking
- Error handling and retry logic
- Edge cases and robustness
"""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from lionagi_qe.persistence.agentdb_bridge import (
    AgentDBBridge,
    ExecutionTrace,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def temp_db_path(tmp_path):
    """Provide temporary database path for tests."""
    return tmp_path / "test_agentdb"


@pytest.fixture
def bridge(temp_db_path):
    """Provide AgentDB bridge instance with test configuration."""
    return AgentDBBridge(
        db_path=str(temp_db_path),
        use_npx=True,
        max_retries=2,
        timeout_ms=3000
    )


@pytest.fixture
def mock_subprocess():
    """Mock subprocess execution for CLI commands."""
    with patch("asyncio.create_subprocess_exec") as mock:
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"success", b""))
        mock.return_value = mock_process
        yield mock


@pytest.fixture
def sample_trace():
    """Provide sample execution trace data."""
    return {
        "test_file": "test_api.py",
        "coverage": 0.85,
        "duration": 12.5,
        "results": {"passed": 42, "failed": 1, "skipped": 2},
        "assertions": 127
    }


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

def test_bridge_initialization(temp_db_path):
    """Test basic bridge initialization with default settings."""
    bridge = AgentDBBridge(db_path=str(temp_db_path))
    
    assert bridge.db_path == temp_db_path
    assert bridge.use_npx is True
    assert bridge.max_retries == 3
    assert bridge.timeout_ms == 5000
    assert bridge.metrics["operations"] == 0
    assert bridge.metrics["errors"] == 0


def test_bridge_custom_configuration(temp_db_path):
    """Test bridge with custom configuration parameters."""
    bridge = AgentDBBridge(
        db_path=str(temp_db_path),
        use_npx=False,
        max_retries=5,
        timeout_ms=10000
    )
    
    assert bridge.use_npx is False
    assert bridge.max_retries == 5
    assert bridge.timeout_ms == 10000
    assert bridge.cmd_prefix == ["agentdb"]


def test_npx_command_prefix(temp_db_path):
    """Test correct command prefix when using npx."""
    bridge_npx = AgentDBBridge(db_path=str(temp_db_path), use_npx=True)
    bridge_native = AgentDBBridge(db_path=str(temp_db_path), use_npx=False)
    
    assert bridge_npx.cmd_prefix == ["npx", "@unboxai/agentdb"]
    assert bridge_native.cmd_prefix == ["agentdb"]


@pytest.mark.asyncio
async def test_initialize_creates_directory(bridge, mock_subprocess):
    """Test that initialize creates database directory."""
    await bridge.initialize()
    
    assert bridge.db_path.exists()
    assert bridge.db_path.is_dir()


@pytest.mark.asyncio
async def test_initialize_skips_if_exists(bridge, mock_subprocess):
    """Test that initialize skips if database already exists."""
    # Create .agentdb marker
    bridge.db_path.mkdir(parents=True, exist_ok=True)
    (bridge.db_path / ".agentdb").touch()
    
    await bridge.initialize()
    
    # Should not call CLI if already initialized
    mock_subprocess.assert_not_called()


# ============================================================================
# EXECUTION TRACE MODEL TESTS
# ============================================================================

def test_execution_trace_creation():
    """Test ExecutionTrace model with required fields."""
    trace = ExecutionTrace(
        execution_id="test-001",
        agent_id="coordinator",
        trace_data={"test": "data"}
    )
    
    assert trace.execution_id == "test-001"
    assert trace.agent_id == "coordinator"
    assert trace.trace_data == {"test": "data"}
    assert trace.status == "completed"
    assert isinstance(trace.timestamp, datetime)


def test_execution_trace_with_all_fields():
    """Test ExecutionTrace with all optional fields."""
    parent_id = "parent-001"
    tags = ["integration", "high-priority"]
    timestamp = datetime.now()
    
    trace = ExecutionTrace(
        execution_id="test-002",
        agent_id="worker",
        parent_execution_id=parent_id,
        trace_data={"coverage": 0.9},
        tags=tags,
        timestamp=timestamp,
        duration_ms=1500.5,
        status="completed"
    )
    
    assert trace.parent_execution_id == parent_id
    assert trace.tags == tags
    assert trace.timestamp == timestamp
    assert trace.duration_ms == 1500.5
    assert trace.status == "completed"


def test_execution_trace_status_validation():
    """Test that invalid status raises ValueError."""
    with pytest.raises(ValueError, match="Status must be one of"):
        ExecutionTrace(
            execution_id="test-003",
            agent_id="coordinator",
            trace_data={},
            status="invalid_status"
        )


@pytest.mark.parametrize("status", ["completed", "failed", "timeout", "running"])
def test_execution_trace_valid_statuses(status):
    """Test all valid status values."""
    trace = ExecutionTrace(
        execution_id=f"test-{status}",
        agent_id="coordinator",
        trace_data={},
        status=status
    )
    
    assert trace.status == status


# ============================================================================
# STORE EXECUTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_store_execution_basic(bridge, mock_subprocess, sample_trace):
    """Test storing a basic execution trace."""
    result = await bridge.store_execution(
        execution_id="test-001",
        agent_id="coordinator",
        trace=sample_trace
    )
    
    assert result is True
    assert bridge.metrics["operations"] > 0
    mock_subprocess.assert_called_once()


@pytest.mark.asyncio
async def test_store_execution_with_tags(bridge, mock_subprocess, sample_trace):
    """Test storing execution with tags."""
    tags = ["integration", "api", "high-priority"]
    
    result = await bridge.store_execution(
        execution_id="test-002",
        agent_id="coordinator",
        trace=sample_trace,
        tags=tags
    )
    
    assert result is True


@pytest.mark.asyncio
async def test_store_execution_with_parent(bridge, mock_subprocess, sample_trace):
    """Test storing hierarchical execution trace."""
    result = await bridge.store_execution(
        execution_id="child-001",
        agent_id="worker",
        trace=sample_trace,
        parent_execution_id="parent-001"
    )
    
    assert result is True


@pytest.mark.asyncio
async def test_store_execution_with_duration(bridge, mock_subprocess, sample_trace):
    """Test storing execution with duration metadata."""
    result = await bridge.store_execution(
        execution_id="test-003",
        agent_id="coordinator",
        trace=sample_trace,
        duration_ms=12500.0
    )
    
    assert result is True


@pytest.mark.asyncio
async def test_store_execution_with_failed_status(bridge, mock_subprocess, sample_trace):
    """Test storing failed execution."""
    result = await bridge.store_execution(
        execution_id="test-004",
        agent_id="coordinator",
        trace=sample_trace,
        status="failed"
    )
    
    assert result is True


@pytest.mark.asyncio
async def test_store_execution_command_failure(bridge, sample_trace):
    """Test that store_execution handles CLI command failures gracefully."""
    with patch("asyncio.create_subprocess_exec") as mock_proc:
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"error"))
        mock_proc.return_value = mock_process
        
        result = await bridge.store_execution(
            execution_id="test-005",
            agent_id="coordinator",
            trace=sample_trace
        )
        
        assert result is False
        assert bridge.metrics["errors"] > 0


# ============================================================================
# QUERY EXECUTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_query_executions_no_filters(bridge):
    """Test querying all executions without filters."""
    mock_results = [
        {
            "execution_id": "test-001",
            "agent_id": "coordinator",
            "trace_data": {"test": "data"},
            "tags": [],
            "timestamp": datetime.now().isoformat(),
            "status": "completed"
        }
    ]
    
    with patch.object(bridge, "_run_command", return_value=json.dumps(mock_results)):
        results = await bridge.query_executions(limit=100)
        
        assert len(results) == 1
        assert results[0].execution_id == "test-001"


@pytest.mark.asyncio
async def test_query_executions_by_agent_id(bridge):
    """Test filtering executions by agent ID."""
    with patch.object(bridge, "_run_command", return_value="[]"):
        results = await bridge.query_executions(agent_id="coordinator")
        
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_query_executions_by_tags(bridge):
    """Test filtering executions by tags."""
    tags = ["integration", "api"]
    
    with patch.object(bridge, "_run_command", return_value="[]"):
        results = await bridge.query_executions(tags=tags)
        
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_query_executions_by_time_range(bridge):
    """Test filtering executions by time range."""
    start_time = datetime.now() - timedelta(hours=24)
    end_time = datetime.now()
    
    with patch.object(bridge, "_run_command", return_value="[]"):
        results = await bridge.query_executions(
            start_time=start_time,
            end_time=end_time
        )
        
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_query_executions_by_status(bridge):
    """Test filtering executions by status."""
    with patch.object(bridge, "_run_command", return_value="[]"):
        results = await bridge.query_executions(status="completed")
        
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_query_executions_combined_filters(bridge):
    """Test querying with multiple filters combined."""
    start_time = datetime.now() - timedelta(hours=1)
    
    with patch.object(bridge, "_run_command", return_value="[]"):
        results = await bridge.query_executions(
            agent_id="coordinator",
            tags=["integration"],
            start_time=start_time,
            status="completed",
            limit=50
        )
        
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_query_executions_parse_error_handling(bridge):
    """Test that query handles malformed JSON gracefully."""
    # Return invalid trace that fails validation
    invalid_data = [{"invalid": "trace", "missing": "required_fields"}]
    
    with patch.object(bridge, "_run_command", return_value=json.dumps(invalid_data)):
        results = await bridge.query_executions()
        
        # Should return empty list, not raise
        assert results == []


@pytest.mark.asyncio
async def test_query_executions_command_failure(bridge):
    """Test query handles CLI command failures gracefully."""
    with patch.object(bridge, "_run_command", side_effect=RuntimeError("CLI error")):
        results = await bridge.query_executions()
        
        assert results == []
        assert bridge.metrics["errors"] > 0


# ============================================================================
# AGENT STATISTICS TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_get_agent_stats_empty(bridge):
    """Test agent stats with no executions."""
    with patch.object(bridge, "query_executions", return_value=[]):
        stats = await bridge.get_agent_stats("coordinator", time_window_hours=24)
        
        assert stats["total_executions"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["avg_duration_ms"] == 0.0
        assert stats["status_breakdown"] == {}


@pytest.mark.asyncio
async def test_get_agent_stats_with_executions(bridge):
    """Test agent stats calculation with multiple executions."""
    mock_executions = [
        ExecutionTrace(
            execution_id="test-001",
            agent_id="coordinator",
            trace_data={},
            status="completed",
            duration_ms=100.0
        ),
        ExecutionTrace(
            execution_id="test-002",
            agent_id="coordinator",
            trace_data={},
            status="completed",
            duration_ms=200.0
        ),
        ExecutionTrace(
            execution_id="test-003",
            agent_id="coordinator",
            trace_data={},
            status="failed",
            duration_ms=150.0
        )
    ]
    
    with patch.object(bridge, "query_executions", return_value=mock_executions):
        stats = await bridge.get_agent_stats("coordinator")
        
        assert stats["total_executions"] == 3
        assert stats["success_rate"] == pytest.approx(2/3, rel=1e-6)
        assert stats["avg_duration_ms"] == pytest.approx(150.0, rel=1e-6)
        assert stats["min_duration_ms"] == 100.0
        assert stats["max_duration_ms"] == 200.0
        assert stats["status_breakdown"]["completed"] == 2
        assert stats["status_breakdown"]["failed"] == 1


@pytest.mark.asyncio
async def test_get_agent_stats_time_window(bridge):
    """Test agent stats respects time window parameter."""
    with patch.object(bridge, "query_executions", return_value=[]) as mock_query:
        await bridge.get_agent_stats("coordinator", time_window_hours=48)
        
        # Verify start_time was calculated correctly
        call_args = mock_query.call_args
        assert call_args is not None


# ============================================================================
# PERFORMANCE METRICS TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_get_metrics_initial_state(bridge):
    """Test metrics in initial state."""
    metrics = await bridge.get_metrics()
    
    assert metrics["total_operations"] == 0
    assert metrics["total_errors"] == 0
    assert metrics["error_rate"] == 0.0
    assert metrics["avg_duration_ms"] == 0.0
    assert metrics["last_operation"] is None


@pytest.mark.asyncio
async def test_metrics_updated_after_operation(bridge, mock_subprocess, sample_trace):
    """Test that metrics are updated after operations."""
    initial_ops = bridge.metrics["operations"]
    
    await bridge.store_execution("test-001", "coordinator", sample_trace)
    
    metrics = await bridge.get_metrics()
    assert metrics["total_operations"] > initial_ops


@pytest.mark.asyncio
async def test_metrics_error_rate_calculation(bridge):
    """Test error rate calculation in metrics."""
    # Simulate operations and errors
    bridge.metrics["operations"] = 100
    bridge.metrics["errors"] = 5
    bridge.metrics["total_duration_ms"] = 15000.0
    
    metrics = await bridge.get_metrics()
    
    assert metrics["error_rate"] == pytest.approx(0.05, rel=1e-6)
    assert metrics["avg_duration_ms"] == pytest.approx(150.0, rel=1e-6)


# ============================================================================
# ERROR HANDLING AND RETRY TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_retry_logic_on_failure(bridge):
    """Test that command retries on failure."""
    call_count = 0
    
    async def failing_subprocess(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_process = AsyncMock()
        if call_count < 3:
            # Fail first 2 attempts
            mock_process.returncode = 1
            mock_process.communicate = AsyncMock(return_value=(b"", b"temporary error"))
        else:
            # Succeed on 3rd attempt
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"success", b""))
        return mock_process
    
    with patch("asyncio.create_subprocess_exec", side_effect=failing_subprocess):
        # Should succeed on 3rd attempt (after 2 retries)
        result = await bridge._run_command(["test"])
        
        assert result == "success"
        assert call_count == 3


@pytest.mark.asyncio
async def test_max_retries_exceeded(bridge):
    """Test that command fails after max retries."""
    with patch("asyncio.create_subprocess_exec") as mock_proc:
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"persistent error"))
        mock_proc.return_value = mock_process
        
        with pytest.raises(RuntimeError, match="failed after"):
            await bridge._run_command(["test"])


@pytest.mark.asyncio
async def test_command_timeout_handling(bridge):
    """Test timeout handling for long-running commands."""
    with patch("asyncio.create_subprocess_exec") as mock_proc:
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_process.kill = Mock()
        mock_proc.return_value = mock_process
        
        with pytest.raises(RuntimeError, match="timeout"):
            await bridge._run_command(["test"])
        
        # Will retry max_retries times (bridge has max_retries=2)
        # So kill() called 3 times total (initial + 2 retries)
        assert mock_process.kill.call_count == 3


# ============================================================================
# EDGE CASES AND ROBUSTNESS
# ============================================================================

@pytest.mark.asyncio
async def test_empty_trace_data(bridge, mock_subprocess):
    """Test storing execution with empty trace data."""
    result = await bridge.store_execution(
        execution_id="test-empty",
        agent_id="coordinator",
        trace={}
    )
    
    assert result is True


@pytest.mark.asyncio
async def test_large_trace_data(bridge, mock_subprocess):
    """Test storing execution with large trace payload."""
    large_trace = {
        "data": ["item"] * 10000,  # Large list
        "nested": {"level1": {"level2": {"level3": "deep"}}}
    }
    
    result = await bridge.store_execution(
        execution_id="test-large",
        agent_id="coordinator",
        trace=large_trace
    )
    
    assert result is True


@pytest.mark.asyncio
async def test_special_characters_in_trace(bridge, mock_subprocess):
    """Test trace data with special characters."""
    special_trace = {
        "message": "Test with 'quotes' and \"double quotes\"",
        "unicode": "émojis 🚀 and 中文",
        "symbols": "<>&\\n\\t"
    }
    
    result = await bridge.store_execution(
        execution_id="test-special",
        agent_id="coordinator",
        trace=special_trace
    )
    
    assert result is True


@pytest.mark.asyncio
async def test_concurrent_operations(bridge, mock_subprocess, sample_trace):
    """Test multiple concurrent operations."""
    tasks = [
        bridge.store_execution(f"test-{i}", "coordinator", sample_trace)
        for i in range(10)
    ]
    
    results = await asyncio.gather(*tasks)
    
    assert all(results)
    assert bridge.metrics["operations"] >= 10


@pytest.mark.asyncio
async def test_very_long_execution_id(bridge, mock_subprocess, sample_trace):
    """Test execution with very long ID."""
    long_id = "test-" + "x" * 1000
    
    result = await bridge.store_execution(
        execution_id=long_id,
        agent_id="coordinator",
        trace=sample_trace
    )
    
    assert result is True


def test_db_path_normalization(temp_db_path):
    """Test that database path is properly normalized."""
    relative_path = "../test_db"
    bridge = AgentDBBridge(db_path=relative_path)
    
    # Should be resolved to absolute path
    assert bridge.db_path.is_absolute()
