"""System implementations — import via the full scenario path, e.g.
``from antomnievo.system.text2sql.dp_text2sql_system import DPText2SQLSystem``.
Kept free of eager imports so one scenario does not pull in another's dependencies
(langchain/langgraph back the optional ``[rag]`` extra used by ``ReactAgentSystem``)."""
