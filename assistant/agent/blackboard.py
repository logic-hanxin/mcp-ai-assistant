"""
Blackboard - 黑板模式通信机制

一种基于共享状态的多Agent通信模式：
- 所有 Agent 共享一个全局状态（黑板）
- 信息可以异步写入和读取
- 支持事件触发机制

核心概念:
- shared_memory: 全局共享上下文
- known_entities: 已发现的实体（用户、文件、数据等）
- intermediate_results: 各步骤中间结果
- event_bus: 事件总线（用于触发其他Agent）
"""

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable


@dataclass
class Entity:
    """已发现的实体"""
    entity_type: str      # user / file / contact / data / location
    key: str             # 实体标识
    value: Any           # 实体值
    source: str          # 来源工具
    confidence: float    # 置信度
    discovered_at: str   # 发现时间


@dataclass
class IntermediateResult:
    """中间结果"""
    step_id: str
    milestone: str
    tool_name: str
    result: str
    timestamp: str


@dataclass
class BlackboardEvent:
    """黑板事件"""
    event_type: str      # entity_discovered / result_ready / task_completed
    source: str          # 事件来源
    data: Any           # 事件数据
    timestamp: str


class Blackboard:
    """
    黑板单例 - 多Agent共享状态

    使用方式:
    ```python
    bb = Blackboard.get_instance()
    bb.write_entity("contact", "张三", "138xxxx", "list_contacts", 0.9)
    bb.write_result("step_1", "milestone_1", "get_weather", "北京: 晴 25度")

    # 读取所有已发现的联系人
    contacts = bb.get_entities("contact")
    ```
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._shared_memory: dict[str, Any] = {}    # 全局共享变量
        self._entities: dict[str, list[Entity]] = {}  # entity_type -> [Entity]
        self._intermediate_results: list[IntermediateResult] = []  # 中间结果
        self._event_handlers: dict[str, list[Callable]] = {}  # event_type -> [handlers]
        self._lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> 'Blackboard':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """重置黑板（测试用）"""
        with cls._lock:
            if cls._instance:
                cls._instance._shared_memory.clear()
                cls._instance._entities.clear()
                cls._instance._intermediate_results.clear()
                cls._instance._event_handlers.clear()

    # ============ 实体管理 ============

    def write_entity(
        self,
        entity_type: str,
        key: str,
        value: Any,
        source: str,
        confidence: float = 1.0,
    ):
        """写入实体到黑板"""
        with self._lock:
            entity = Entity(
                entity_type=entity_type,
                key=key,
                value=value,
                source=source,
                confidence=confidence,
                discovered_at=datetime.now().isoformat(),
            )

            if entity_type not in self._entities:
                self._entities[entity_type] = []

            # 检查是否已存在，存在的更新
            for i, e in enumerate(self._entities[entity_type]):
                if e.key == key:
                    self._entities[entity_type][i] = entity
                    self._emit_event("entity_updated", source, entity)
                    return

            self._entities[entity_type].append(entity)
            self._emit_event("entity_discovered", source, entity)

    def get_entities(self, entity_type: str) -> list[Entity]:
        """获取指定类型的所有实体"""
        with self._lock:
            return list(self._entities.get(entity_type, []))

    def get_entity(self, entity_type: str, key: str) -> Entity | None:
        """获取指定实体"""
        with self._lock:
            for e in self._entities.get(entity_type, []):
                if e.key == key:
                    return e
            return None

    def find_entities(self, **kwargs) -> list[Entity]:
        """按条件查找实体"""
        with self._lock:
            results = []
            for entities in self._entities.values():
                for e in entities:
                    match = True
                    for k, v in kwargs.items():
                        if getattr(e, k, None) != v:
                            match = False
                            break
                    if match:
                        results.append(e)
            return results

    # ============ 共享变量 ============

    def set(self, key: str, value: Any):
        """设置共享变量"""
        with self._lock:
            old_value = self._shared_memory.get(key)
            self._shared_memory[key] = value

            if old_value != value:
                self._emit_event("variable_changed", "blackboard", {
                    "key": key,
                    "old_value": old_value,
                    "new_value": value,
                })

    def get(self, key: str, default: Any = None) -> Any:
        """获取共享变量"""
        with self._lock:
            return self._shared_memory.get(key, default)

    def get_all_variables(self) -> dict[str, Any]:
        """获取所有共享变量"""
        with self._lock:
            return dict(self._shared_memory)

    # ============ 中间结果 ============

    def write_result(
        self,
        step_id: str,
        milestone: str,
        tool_name: str,
        result: str,
    ):
        """写入中间结果"""
        with self._lock:
            ir = IntermediateResult(
                step_id=step_id,
                milestone=milestone,
                tool_name=tool_name,
                result=result,
                timestamp=datetime.now().isoformat(),
            )
            self._intermediate_results.append(ir)
            self._emit_event("result_ready", tool_name, ir)

    def get_results(self, milestone: str = None, step_id: str = None) -> list[IntermediateResult]:
        """获取中间结果"""
        with self._lock:
            results = self._intermediate_results
            if milestone:
                results = [r for r in results if r.milestone == milestone]
            if step_id:
                results = [r for r in results if r.step_id == step_id]
            return list(results)

    # ============ 事件系统 ============

    def subscribe(self, event_type: str, handler: Callable):
        """订阅事件"""
        with self._lock:
            if event_type not in self._event_handlers:
                self._event_handlers[event_type] = []
            if handler not in self._event_handlers[event_type]:
                self._event_handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable):
        """取消订阅"""
        with self._lock:
            if event_type in self._event_handlers:
                self._event_handlers[event_type] = [
                    h for h in self._event_handlers[event_type] if h != handler
                ]

    def _emit_event(self, event_type: str, source: str, data: Any):
        """触发事件"""
        event = BlackboardEvent(
            event_type=event_type,
            source=source,
            data=data,
            timestamp=datetime.now().isoformat(),
        )

        handlers = self._event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                print(f"[Blackboard] 事件处理失败: {e}")

    # ============ 调试工具 ============

    def dump(self) -> dict:
        """导出黑板状态（调试用）"""
        with self._lock:
            return {
                "shared_memory": self._shared_memory,
                "entities": {
                    k: [
                        {
                            "entity_type": e.entity_type,
                            "key": e.key,
                            "value": str(e.value)[:100],
                            "source": e.source,
                            "confidence": e.confidence,
                            "discovered_at": e.discovered_at,
                        }
                        for e in entities
                    ]
                    for k, entities in self._entities.items()
                },
                "intermediate_results": [
                    {
                        "step_id": r.step_id,
                        "milestone": r.milestone,
                        "tool_name": r.tool_name,
                        "result": r.result[:100],
                        "timestamp": r.timestamp,
                    }
                    for r in self._intermediate_results[-10:]  # 最近10条
                ],
            }

    def __repr__(self) -> str:
        return f"Blackboard(entities={len(self._entities)}, results={len(self._intermediate_results)})"
