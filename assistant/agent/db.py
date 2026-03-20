"""
数据库兼容出口

新代码请优先按领域引用:
- assistant.agent.db_core
- assistant.agent.db_memory
- assistant.agent.db_contacts
- assistant.agent.db_workflow
- assistant.agent.db_knowledge
- assistant.agent.db_misc

此模块暂时保留，避免一次性改动所有调用方。
"""

from assistant.agent.db_core import get_connection, init_tables
from assistant.agent.db_memory import (
    clear_session_messages,
    count_messages,
    delete_old_messages,
    load_facts,
    load_recent_messages,
    load_summaries,
    save_fact,
    save_message,
    save_summary,
)
from assistant.agent.db_contacts import (
    contact_get_groups,
    contact_get_user,
    contact_get_user_display_name,
    contact_get_users,
    contact_set_group_name,
    contact_set_user_name,
    contact_upsert_group,
    contact_upsert_user,
)
from assistant.agent.db_workflow import (
    workflow_create,
    workflow_delete,
    workflow_get,
    workflow_get_due,
    workflow_list,
    workflow_toggle,
    workflow_update_after_run,
)
from assistant.agent.db_knowledge import (
    knowledge_add_chunk,
    knowledge_add_chunks_batch,
    knowledge_add_doc,
    knowledge_delete_doc,
    knowledge_get_all_chunks_with_embedding,
    knowledge_list_docs,
    knowledge_search_fulltext,
    knowledge_search_like,
    knowledge_update_doc_chunks,
)
from assistant.agent.db_misc import (
    delete_rule,
    github_watch_add,
    github_watch_list,
    github_watch_remove,
    github_watch_update_sha,
    load_rules,
    load_rules_text,
    monitor_add_site,
    monitor_get_sites,
    monitor_remove_site,
    monitor_update_site,
    news_state_get,
    news_state_set,
    note_create,
    note_delete,
    note_list,
    note_search,
    reminder_create,
    reminder_delete,
    reminder_get_all_pending,
    reminder_get_pending,
    reminder_mark_triggered,
    save_lesson,
    save_rule,
    search_lessons,
)
