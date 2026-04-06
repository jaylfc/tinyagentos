"""Built-in agent templates — pre-configured agent personas for one-click deploy."""
from __future__ import annotations

CATEGORIES = [
    "productivity", "development", "marketing", "finance",
    "education", "creative", "customer-support", "research",
    "devops", "data-science", "legal", "hr",
]

TEMPLATES = [
    {
        "id": "research-assistant",
        "name": "Research Assistant",
        "category": "research",
        "description": "Searches the web, summarises papers, and compiles research briefs",
        "framework": "smolagents",
        "model": "qwen3-8b",
        "system_prompt": "You are a research assistant. Your job is to help the user find, summarise, and organise information. Always cite your sources. Present findings in clear, structured format with key takeaways first.",
        "color": "#4ecdc4",
        "memory_limit": "2GB",
        "cpu_limit": 2,
    },
    {
        "id": "code-reviewer",
        "name": "Code Reviewer",
        "category": "development",
        "description": "Reviews pull requests, finds bugs, suggests improvements",
        "framework": "smolagents",
        "model": "qwen3-8b",
        "system_prompt": "You are a senior code reviewer. Review code for bugs, security issues, performance problems, and style inconsistencies. Be constructive and specific. Always explain why something is a problem and suggest a fix.",
        "color": "#ff6b6b",
        "memory_limit": "2GB",
        "cpu_limit": 2,
    },
    {
        "id": "content-writer",
        "name": "Content Writer",
        "category": "marketing",
        "description": "Writes blog posts, social media copy, and marketing content",
        "framework": "smolagents",
        "model": "qwen3-4b",
        "system_prompt": "You are a professional content writer. Write engaging, clear, and persuasive content. Adapt your tone to the target audience. Use active voice, short paragraphs, and compelling headlines.",
        "color": "#ffd93d",
        "memory_limit": "1GB",
        "cpu_limit": 1,
    },
    {
        "id": "customer-support",
        "name": "Customer Support Agent",
        "category": "customer-support",
        "description": "Handles customer inquiries, troubleshoots issues, escalates when needed",
        "framework": "smolagents",
        "model": "qwen3-4b",
        "system_prompt": "You are a friendly customer support agent. Help customers resolve their issues quickly and professionally. If you cannot solve a problem, acknowledge it and offer to escalate. Always be empathetic and patient.",
        "color": "#45b7d1",
        "memory_limit": "1GB",
        "cpu_limit": 1,
    },
    {
        "id": "data-analyst",
        "name": "Data Analyst",
        "category": "data-science",
        "description": "Analyses datasets, creates summaries, identifies trends and anomalies",
        "framework": "smolagents",
        "model": "qwen3-8b",
        "system_prompt": "You are a data analyst. Analyse data to find patterns, trends, and insights. Present findings with clear visualisation descriptions and actionable recommendations. Always note data quality issues and limitations.",
        "color": "#96ceb4",
        "memory_limit": "2GB",
        "cpu_limit": 2,
    },
    {
        "id": "meeting-summariser",
        "name": "Meeting Summariser",
        "category": "productivity",
        "description": "Summarises meeting transcripts into action items and key decisions",
        "framework": "smolagents",
        "model": "qwen3-4b",
        "system_prompt": "You are a meeting summariser. Given a meeting transcript, extract: 1) Key decisions made, 2) Action items with owners and deadlines, 3) Open questions, 4) Brief summary (3-5 sentences). Be concise and structured.",
        "color": "#dda0dd",
        "memory_limit": "1GB",
        "cpu_limit": 1,
    },
    {
        "id": "devops-assistant",
        "name": "DevOps Assistant",
        "category": "devops",
        "description": "Helps with CI/CD, Docker, Kubernetes, infrastructure automation",
        "framework": "smolagents",
        "model": "qwen3-8b",
        "system_prompt": "You are a DevOps engineer. Help with infrastructure automation, CI/CD pipelines, containerisation, monitoring, and deployment. Prioritise reliability, security, and reproducibility. Suggest infrastructure-as-code approaches.",
        "color": "#ff8c42",
        "memory_limit": "2GB",
        "cpu_limit": 2,
    },
    {
        "id": "tutor",
        "name": "Personal Tutor",
        "category": "education",
        "description": "Explains concepts, creates practice exercises, adapts to learning level",
        "framework": "smolagents",
        "model": "qwen3-4b",
        "system_prompt": "You are a patient and encouraging tutor. Explain concepts clearly using analogies and examples. Check understanding by asking questions. Adapt your explanations to the learner's level. Break complex topics into manageable steps.",
        "color": "#a8e6cf",
        "memory_limit": "1GB",
        "cpu_limit": 1,
    },
    {
        "id": "creative-writer",
        "name": "Creative Writer",
        "category": "creative",
        "description": "Writes stories, poetry, scripts, and creative fiction",
        "framework": "smolagents",
        "model": "qwen3-8b",
        "system_prompt": "You are a creative writer. Write engaging fiction, poetry, and scripts with vivid imagery and compelling characters. Experiment with different styles and genres. Help users develop their creative ideas into polished pieces.",
        "color": "#e056a0",
        "memory_limit": "2GB",
        "cpu_limit": 2,
    },
    {
        "id": "finance-advisor",
        "name": "Finance Advisor",
        "category": "finance",
        "description": "Analyses financial data, explains concepts, helps with budgeting",
        "framework": "smolagents",
        "model": "qwen3-8b",
        "system_prompt": "You are a financial advisor. Help with budgeting, financial analysis, and explaining financial concepts. Always note that you provide general information, not personalised financial advice. Be precise with numbers and cite relevant regulations.",
        "color": "#2ecc71",
        "memory_limit": "2GB",
        "cpu_limit": 2,
    },
    {
        "id": "legal-assistant",
        "name": "Legal Research Assistant",
        "category": "legal",
        "description": "Researches legal topics, summarises regulations, drafts documents",
        "framework": "smolagents",
        "model": "qwen3-8b",
        "system_prompt": "You are a legal research assistant. Help find relevant laws, regulations, and case precedents. Summarise legal documents in plain language. Always note that you provide legal information, not legal advice, and recommend consulting a qualified lawyer.",
        "color": "#8b7355",
        "memory_limit": "2GB",
        "cpu_limit": 2,
    },
    {
        "id": "hr-assistant",
        "name": "HR Assistant",
        "category": "hr",
        "description": "Helps with job descriptions, interview questions, HR policies",
        "framework": "smolagents",
        "model": "qwen3-4b",
        "system_prompt": "You are an HR assistant. Help draft job descriptions, create interview questions, summarise HR policies, and assist with employee communications. Be inclusive and professional. Follow best practices for diversity and compliance.",
        "color": "#c39bd3",
        "memory_limit": "1GB",
        "cpu_limit": 1,
    },
]


EXTERNAL_SOURCES = [
    {
        "id": "awesome-openclaw",
        "name": "Awesome OpenClaw Agents",
        "repo": "mergisi/awesome-openclaw-agents",
        "description": "202 agent personas across 24 categories",
        "url": "https://github.com/mergisi/awesome-openclaw-agents",
        "license": "MIT",
        "format": "soul-md",
        "count": 202,
    },
    {
        "id": "system-prompt-library",
        "name": "System Prompt Library",
        "repo": "danielrosehill/System-Prompt-Library",
        "description": "937+ system prompts with metadata and capability flags",
        "url": "https://github.com/danielrosehill/System-Prompt-Library",
        "license": "CC BY 4.0",
        "format": "json",
        "count": 937,
    },
]


async def fetch_external_index(source_id: str, http_client) -> list[dict]:
    """Fetch template index from an external GitHub source via the API.
    Returns a list of template stubs (id, name, category, path) without full content."""
    source = next((s for s in EXTERNAL_SOURCES if s["id"] == source_id), None)
    if not source:
        return []

    repo = source["repo"]
    try:
        if source["format"] == "soul-md":
            # Fetch the repo tree to find SOUL.md files
            resp = await http_client.get(
                f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1",
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=15,
            )
            if resp.status_code != 200:
                return []
            tree = resp.json().get("tree", [])
            templates = []
            for item in tree:
                path = item.get("path", "")
                if path.endswith("/SOUL.md") and path.startswith("agents/"):
                    parts = path.split("/")
                    if len(parts) >= 3:
                        category = parts[1]
                        name = parts[2]
                        templates.append({
                            "id": f"{source_id}:{name}",
                            "name": name.replace("-", " ").title(),
                            "category": category,
                            "source": source_id,
                            "path": path,
                            "description": f"{category} agent from {source['name']}",
                        })
            return templates

        elif source["format"] == "json":
            resp = await http_client.get(
                f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1",
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=15,
            )
            if resp.status_code != 200:
                return []
            tree = resp.json().get("tree", [])
            templates = []
            for item in tree:
                path = item.get("path", "")
                if path.startswith("system-prompts/json/") and path.endswith(".json"):
                    filename = path.rsplit("/", 1)[-1].replace(".json", "")
                    templates.append({
                        "id": f"{source_id}:{filename}",
                        "name": filename.replace("-", " ").replace("_", " ").title(),
                        "category": "general",
                        "source": source_id,
                        "path": path,
                        "description": f"System prompt from {source['name']}",
                    })
            return templates

    except Exception:
        return []

    return []


async def fetch_external_template(source_id: str, path: str, http_client) -> dict | None:
    """Fetch the full content of a single external template."""
    source = next((s for s in EXTERNAL_SOURCES if s["id"] == source_id), None)
    if not source:
        return None

    repo = source["repo"]
    try:
        raw_url = f"https://raw.githubusercontent.com/{repo}/main/{path}"
        resp = await http_client.get(raw_url, timeout=10)
        if resp.status_code != 200:
            return None

        if source["format"] == "soul-md":
            content = resp.text
            parts = path.split("/")
            category = parts[1] if len(parts) >= 2 else "general"
            name = parts[2] if len(parts) >= 3 else "agent"
            return {
                "id": f"{source_id}:{name}",
                "name": name.replace("-", " ").title(),
                "category": category,
                "source": source_id,
                "framework": "openclaw",
                "model": "qwen3-4b",
                "system_prompt": content,
                "color": "#888888",
                "memory_limit": "1GB",
                "cpu_limit": 1,
            }

        elif source["format"] == "json":
            import json
            data = json.loads(resp.text)
            return {
                "id": f"{source_id}:{path.rsplit('/', 1)[-1].replace('.json', '')}",
                "name": data.get("agent_name", data.get("title", "Agent")),
                "category": "general",
                "source": source_id,
                "framework": "smolagents",
                "model": "qwen3-4b",
                "system_prompt": data.get("System Prompt", data.get("system_prompt", "")),
                "description": data.get("Description", data.get("description", "")),
                "color": "#888888",
                "memory_limit": "1GB",
                "cpu_limit": 1,
            }

    except Exception:
        return None

    return None


def list_templates(category: str | None = None) -> list[dict]:
    """Return all templates, optionally filtered by category."""
    if category:
        return [t for t in TEMPLATES if t["category"] == category]
    return list(TEMPLATES)


def get_template(template_id: str) -> dict | None:
    """Get a single template by ID."""
    return next((t for t in TEMPLATES if t["id"] == template_id), None)
