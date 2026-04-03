# ─────────────────────────────────────────────────────────────────────────────
# ADD THIS TO backend/app/main.py
# Inside the startup_event() function, after existing scheduler jobs
# ─────────────────────────────────────────────────────────────────────────────

# AEM Release Agent — check every 6 hours
aem_agent_enabled  = os.getenv("AEM_RELEASE_AGENT_ENABLED", "true").lower() == "true"
aem_agent_schedule = os.getenv("AEM_RELEASE_AGENT_CRON", "0 */6 * * *")  # every 6 hours

def run_aem_release_agent_job():
    """Scheduled job wrapper for AEM release agent."""
    import asyncio
    try:
        from app.services.aem_release_agent import run_aem_release_agent
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(run_aem_release_agent())
        loop.close()
        logger.info_structured(
            "Scheduled AEM release agent completed",
            extra_fields={
                "action":  result.get("action"),
                "version": result.get("version"),
            },
        )
    except Exception as e:
        logger.error_structured(
            "Scheduled AEM release agent failed",
            extra_fields={"error": str(e)},
            exc_info=True,
        )

if aem_agent_enabled:
    scheduler.add_job(
        run_aem_release_agent_job,
        trigger=CronTrigger.from_crontab(aem_agent_schedule),
        id="aem_release_agent_job",
        name="AEM Release Agent",
        replace_existing=True,
    )
    logger.info_structured(
        "AEM release agent scheduled",
        extra_fields={"cron": aem_agent_schedule},
    )

# ─────────────────────────────────────────────────────────────────────────────
# ADD TO router.py:
# from app.api.v1.routes import agent
# api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# ADD TO .env:
# AEM_RELEASE_AGENT_ENABLED=true
# AEM_RELEASE_AGENT_CRON=0 */6 * * *
# TAVILY_API_KEY=tvly-xxxxxxxxxxxx
# ─────────────────────────────────────────────────────────────────────────────
