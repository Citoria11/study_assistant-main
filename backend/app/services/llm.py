"""
Centralised LLM and embeddings factories.

All LLM calls in the app should go through these helpers so that
the Azure AI Foundry connection details live in exactly one place.
"""

import os

from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings


def get_llm(temperature: float = 0.2) -> AzureChatOpenAI:
    """Return an AzureChatOpenAI instance for the classic Azure OpenAI resource."""
    return AzureChatOpenAI(
        azure_deployment=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        openai_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        temperature=temperature,
    )


def get_embeddings() -> AzureOpenAIEmbeddings:
    """
    Return an AzureOpenAIEmbeddings instance for the embeddings deployment.

    Uses dedicated AZURE_OPENAI_EMBEDDING_* variables because the embeddings
    deployment may live in a different resource with its own endpoint and key.
    AzureOpenAIEmbeddings still uses the traditional Azure path and requires
    an api_version.
    """
    return AzureOpenAIEmbeddings(
        azure_deployment=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
        azure_endpoint=os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT"),
        openai_api_key=os.getenv("AZURE_OPENAI_EMBEDDING_API_KEY"),
        openai_api_version=os.getenv(
            "AZURE_OPENAI_EMBEDDING_API_VERSION", "2024-02-01"
        ),
    )
