from __future__ import annotations

import logging

import typer

from config.settings import DB_PATH, settings
from reviewerfinder.clients.openalex import OpenAlexClient
from reviewerfinder.clients.semantic_scholar import SemanticScholarClient
from reviewerfinder.db.connection import init_db
from reviewerfinder.db.repository import ScholarRepository
from reviewerfinder.pipeline import run_search

app = typer.Typer(help="Find qualified peer-review candidate scholars for a paper.")


@app.command()
def search(
    title: str = typer.Option(..., help="Paper title"),
    abstract: str = typer.Option(None, help="Paper abstract"),
    keywords: str = typer.Option("", help="Comma-separated keywords"),
    results_per_set: int = typer.Option(10, help="Scholars to show per keyword set"),
    max_pages: int = typer.Option(2, help="Max OpenAlex works-search pages to fetch, per keyword set"),
    allowed_countries: str = typer.Option(
        "", help="Comma-separated ISO alpha-2 codes to allow (empty = no allow-list restriction)"
    ),
    excluded_countries: str = typer.Option(
        "", help="Comma-separated ISO alpha-2 codes to always exclude, on top of the built-in rules"
    ),
    manual_keyword_sets: str = typer.Option(
        None,
        help="Semicolon-separated groups of comma-separated keywords for manual search angles, "
        "e.g. 'kw1,kw2;kw3,kw4,kw5' (1-5 groups). Skips Ollama decomposition when given.",
    ),
):
    """Decomposes the paper into 5 keyword-set angles (via a local Ollama
    model), then runs the full discovery -> filter -> rank pipeline
    separately for each one.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    init_db(DB_PATH)

    openalex_client = OpenAlexClient(
        api_key=settings.require_openalex_key(), mailto=settings.openalex_mailto
    )
    s2_client = SemanticScholarClient(api_key=settings.semantic_scholar_api_key)

    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
    allowed_country_list = [c.strip().upper() for c in allowed_countries.split(",") if c.strip()] or None
    excluded_country_list = [c.strip().upper() for c in excluded_countries.split(",") if c.strip()] or None
    manual_sets = (
        [[k.strip() for k in group.split(",") if k.strip()] for group in manual_keyword_sets.split(";")]
        if manual_keyword_sets
        else None
    )

    result = run_search(
        title=title,
        abstract=abstract,
        keywords=keyword_list,
        db_path=DB_PATH,
        openalex_client=openalex_client,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        s2_client=s2_client,
        staleness_months=settings.scholar_staleness_months,
        max_openalex_pages=max_pages,
        results_per_set=results_per_set,
        allowed_countries=allowed_country_list,
        excluded_countries=excluded_country_list,
        manual_keyword_sets=manual_sets,
    )

    typer.echo(f"\nEvaluated {result.evaluated_count} candidate scholars across {len(result.keyword_set_results)} keyword sets.\n")

    for set_result in result.keyword_set_results:
        ks = set_result.keyword_set
        typer.secho(f"Set {ks.set_index} -- {ks.label}  ({', '.join(ks.keywords)})", fg=typer.colors.CYAN, bold=True)

        if len(set_result.passing_scholars) < results_per_set:
            typer.secho(
                f"  Only {len(set_result.passing_scholars)} of {results_per_set} requested scholars passed. "
                "Consider raising --max-pages.",
                fg=typer.colors.YELLOW,
            )

        for rank, (scholar, score) in enumerate(set_result.passing_scholars, start=1):
            topics = ", ".join(t.topic for t in scholar.research_topics[:5])
            typer.echo(f"  {rank}. {scholar.display_name}  (score={score:.3f})")
            typer.echo(f"     Institution: {scholar.current_institution_name} ({scholar.current_institution_country_code}, zone={scholar.zone.value})")
            typer.echo(f"     h-index: {scholar.h_index}   recent papers (5y): {scholar.works_count_last_5y}")
            typer.echo(f"     Email: {scholar.email or '(not found)'}  [{scholar.email_verification_status.value}]")
            typer.echo(f"     Topics: {topics}")
            typer.echo(f"     Profile check: {scholar.gscholar_search_url}")
        typer.echo("")


@app.command()
def refresh():
    """Bulk re-check scholars whose data has exceeded the staleness window."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    init_db(DB_PATH)

    scholar_repo = ScholarRepository(DB_PATH, staleness_months=settings.scholar_staleness_months)
    stale = scholar_repo.list_stale()
    typer.echo(f"{len(stale)} scholars are stale (older than {settings.scholar_staleness_months} months).")

    if not stale:
        return

    openalex_client = OpenAlexClient(
        api_key=settings.require_openalex_key(), mailto=settings.openalex_mailto
    )
    from reviewerfinder.discovery.enrichment import carry_over_email, scholar_from_openalex_author
    from datetime import date

    updated = 0
    for scholar in stale:
        if not scholar.openalex_id:
            continue
        raw_author = openalex_client.get_author(scholar.openalex_id)
        if raw_author is None:
            continue
        refreshed, history = scholar_from_openalex_author(raw_author, date.today())
        refreshed = carry_over_email(refreshed, scholar)
        scholar_repo.upsert(refreshed)
        scholar_repo.replace_affiliation_history(refreshed.id, history)
        updated += 1

    typer.echo(f"Refreshed {updated} scholar records.")


@app.command()
def chat():
    """Interactive chatbot over stored papers/scholars (requires a local Ollama server)."""
    init_db(DB_PATH)

    from reviewerfinder.chatbot.agent import build_chatbot
    from reviewerfinder.chatbot.session import checkpointer_context

    openalex_client = OpenAlexClient(
        api_key=settings.require_openalex_key(), mailto=settings.openalex_mailto
    )

    typer.echo("ScholarFinder chat. Type 'exit' or 'quit' to leave.\n")
    thread_config = {"configurable": {"thread_id": "cli"}}

    with checkpointer_context() as checkpointer:
        agent = build_chatbot(
            db_path=DB_PATH,
            openalex_client=openalex_client,
            checkpointer=checkpointer,
            staleness_months=settings.scholar_staleness_months,
        )

        while True:
            try:
                user_text = typer.prompt("you")
            except (EOFError, KeyboardInterrupt):
                break

            if user_text.strip().lower() in {"exit", "quit"}:
                break

            result = agent.invoke(
                {"messages": [{"role": "user", "content": user_text}]},
                config=thread_config,
            )
            reply = result["messages"][-1].content
            typer.echo(f"assistant: {reply}\n")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8000, help="Bind port"),
    reload: bool = typer.Option(True, help="Auto-reload on code changes (dev mode)"),
):
    """Run the HTTP API that the web frontend talks to.

    Browsing already-stored papers/scholars works without OPENALEX_API_KEY;
    only the /api/papers/search endpoint needs it.
    """
    import uvicorn

    uvicorn.run("reviewerfinder.api.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
