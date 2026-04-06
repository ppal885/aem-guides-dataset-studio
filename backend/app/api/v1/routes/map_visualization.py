"""FastAPI routes for DITA map visualization."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.map_visualizer_service import parse_map_to_graph, graph_to_mermaid

router = APIRouter(prefix="/api/v1/map-viz", tags=["map-visualization"])


class MapVizRequest(BaseModel):
    xml: str


@router.post("/parse")
async def parse_map(req: MapVizRequest):
    """Parse a ditamap and return graph data for visualization."""
    try:
        return parse_map_to_graph(req.xml)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/mermaid")
async def get_mermaid(req: MapVizRequest):
    """Parse a ditamap and return Mermaid.js diagram code."""
    try:
        graph = parse_map_to_graph(req.xml)
        mermaid_code = graph_to_mermaid(graph)
        return {"mermaid": mermaid_code, "title": graph["title"], "stats": graph["stats"]}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
