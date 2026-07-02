import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from base.read_config import read_config
from base.knowledge import KnowledgeBankClientFactory

CSV_PATH = "app/docs/Branch_Revenue_Orders.csv"
CSV_SKILL = Path("app/mcp_server/csv_skill.md").read_text()

load_dotenv(".env")
mcp = FastMCP("acme-tools")


@mcp.tool()
async def similarity_search(collection_name: str, query: str, top_k: int = 0) -> str:
    """Retrieve the most relevant document passages from a knowledge base collection."""
    config = read_config()
    kb = KnowledgeBankClientFactory(config).client
    provider = config["KNOWLEDGE_CONFIG"]["DEFAULT_PROVIDER"]
    provider_config = config["KNOWLEDGE_CONFIG"]["PROVIDERS"][provider]
    if collection_name in provider_config:
        collection_name = provider_config[collection_name]
    matches = await kb.search(query, collection_name, top_k or None)
    if not matches:
        return "No sufficiently relevant passages found in the knowledge base."
    blocks = []
    for match in matches:
        meta = match["metadata"]
        citation = f"{meta.get('document_name')} | {meta.get('section_name', '')} | page {meta.get('page_number')}"
        blocks.append(f"[{citation}] (similarity {match['similarity']})\n{match['document']}")
    return "\n\n".join(blocks)


@mcp.tool(description=CSV_SKILL)
def csv_schema() -> str:
    df = pd.read_csv(CSV_PATH)
    columns = ", ".join(f"{col} ({df[col].dtype})" for col in df.columns)
    return f"Rows: {len(df)}\nColumns: {columns}"


@mcp.tool(description=CSV_SKILL)
def operate_on_csv(code: str) -> str:
    df = pd.read_csv(CSV_PATH)
    results_local = {}
    exec(code, {"df":df}, results_local) # Inject df for use
    result = results_local.get("result") # Get result derived by llm
    if not result:
        # Return tool error if result variable is not initialized in llm generated code
        return f"No variable 'result' present in generated code: {code}" 
    
    return f"Result in variable 'result' : {result}"


@mcp.tool()
def web_search(query: str) -> str:
    """Search the public web for external or current information."""
    from tavily import TavilyClient
    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

    results = client.search(query).get("results", [])

    if not results:
        return "No web results found."
    
    return "\n\n".join(
        f"Title: {r.get('title')} — URL: {r.get('url')}\n Content: {r.get('content')}" for r in results[:5]
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
