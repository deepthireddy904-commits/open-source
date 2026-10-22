"""
Verification test for LangChain Expression Language (LCEL) chain components,
prompt template, and JsonOutputParser with PRChroniclerOutput schema.
"""

from langchain_core.output_parsers import JsonOutputParser
from pr_chronicler.schemas import PRChroniclerOutput, KeyLearning
from pr_chronicler.synthesizer import SYSTEM_PROMPT, USER_PROMPT

def test_lcel_parser_instructions():
    """Ensure JsonOutputParser generates clean schema instructions for Gemini Flash."""
    parser = JsonOutputParser(pydantic_object=PRChroniclerOutput)
    instructions = parser.get_format_instructions()
    assert "issue_details" in instructions
    assert "execution_summary" in instructions
    assert "key_learnings" in instructions
    print("LCEL Parser schema instructions verified:")
    print(instructions[:300] + "...")

def test_pydantic_enforcement():
    """Verify parser parses a realistic model response."""
    parser = JsonOutputParser(pydantic_object=PRChroniclerOutput)
    raw_sample = """```json
    {
        "issue_details": "Fixes connection pool leaks under high concurrency loads.",
        "execution_summary": "Introduced context manager guard around TCP session acquisition and added exponential retry backoff in client session handler.",
        "key_learnings": [
            {
                "category": "Resource Management",
                "insight": "Using scoped context managers guarantees cleanup even during unexpected socket timeouts.",
                "evidence": "src/client.py:with session_pool.acquire() as conn:"
            },
            {
                "category": "Error Handling",
                "insight": "Differentiating between transient network errors and permanent HTTP 4xx errors prevents infinite retry storms.",
                "evidence": "src/retry.py:is_retryable_exception(exc)"
            },
            {
                "category": "Concurrency",
                "insight": "Non-blocking semaphores reduce thread lock contention when polling pool availability.",
                "evidence": "src/pool.py:asyncio.Semaphore(max_connections)"
            }
        ]
    }
    ```"""
    parsed = parser.parse(raw_sample)
    output = PRChroniclerOutput(**parsed)
    assert len(output.key_learnings) == 3
    assert output.key_learnings[0].category == "Resource Management"
    print("Parsed output successfully conforms to strict Pydantic model!")

if __name__ == "__main__":
    test_lcel_parser_instructions()
    test_pydantic_enforcement()
