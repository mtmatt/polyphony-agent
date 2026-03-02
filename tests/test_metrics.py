import time
from polyphony.metrics import MetricsCollector

def test_metrics_collector():
    collector = MetricsCollector()
    
    collector.start_task("task1", "goal1", "model1")
    time.sleep(0.1)
    collector.end_task("task1", True, 10, 20)
    
    summary = collector.get_summary()
    assert summary["total_tasks"] == 1
    assert summary["successful_tasks"] == 1
    assert summary["total_tokens"] == 30
    assert summary["avg_task_duration"] >= 0.1
    assert summary["success_rate"] == 1.0

def test_metrics_collector_failure():
    collector = MetricsCollector()
    
    collector.start_task("task1", "goal1")
    collector.end_task("task1", False)
    
    summary = collector.get_summary()
    assert summary["total_tasks"] == 1
    assert summary["successful_tasks"] == 0
    assert summary["success_rate"] == 0.0
