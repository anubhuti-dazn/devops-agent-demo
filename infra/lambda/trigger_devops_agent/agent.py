"""
DevOps agent interaction: create chat session and process the event stream.
Pattern copied directly from rca-analyser/modules/lambdas/rca-analyser/agent.py.
"""

import logging

from config import AGENT_SPACE_ID, devops_client

logger = logging.getLogger(__name__)


def run_investigation(prompt: str, agent_id: str | None = None) -> dict:
    """
    Creates a chat session, sends the prompt, and returns the processed result.

    Args:
        prompt: The investigation prompt to send to the agent.
        agent_id: Optional override for the agent space ID.

    Returns:
        dict with keys 'content' (str), 'token_usage' (dict), 'execution_id' (str).
    """
    effective_agent_id = agent_id or AGENT_SPACE_ID
    if not effective_agent_id:
        raise ValueError("AGENT_SPACE_ID is not configured. Set it as an environment variable.")

    logger.info("Creating chat execution in agent space: %s", effective_agent_id)
    create_response = devops_client.create_chat(agentSpaceId=effective_agent_id, userType="IAM")
    execution_id = create_response["executionId"]
    logger.info("Chat execution created: %s", execution_id)

    logger.info("Sending investigation prompt (%d chars)...", len(prompt))
    response = devops_client.send_message(
        agentSpaceId=effective_agent_id,
        executionId=execution_id,
        content=prompt,
    )

    result = _process_event_stream(response["events"])
    result["execution_id"] = execution_id
    return result


def _process_event_stream(stream) -> dict:
    """Consume the streaming response and accumulate text + token usage."""
    content_parts = []
    token_usage = {}

    for event in stream:
        if "contentBlockDelta" in event:
            delta = event["contentBlockDelta"]
            if "delta" in delta and "textDelta" in delta["delta"]:
                content_parts.append(delta["delta"]["textDelta"]["text"])
            elif "delta" in delta and "text" in delta["delta"]:
                content_parts.append(delta["delta"]["text"])
        elif "responseCompleted" in event:
            completed = event["responseCompleted"]
            if "usage" in completed:
                token_usage = {
                    "input_tokens": completed["usage"].get("inputTokens", 0),
                    "output_tokens": completed["usage"].get("outputTokens", 0),
                }
            logger.info("Response completed. Tokens: %s", token_usage)
        elif "responseFailed" in event:
            raise Exception(f"Agent response failed: {event['responseFailed']}")

    return {"content": "".join(content_parts), "token_usage": token_usage}
