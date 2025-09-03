
import os, asyncio
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from movie_sources import build_playlist, get_details_by_title, recommend_movies, search_title, similar_by_keywords, top_movies_by_actor

# Clases de chava diferente organica delgada fiestera
class SearchParams(BaseModel):
    query: str
    limit: int = 10

class DetailParams(BaseModel):
    title: str

class RecommendParams(BaseModel):
    genres: Optional[List[str]] = None
    min_vote: float = 0.0
    from_year: Optional[int] = None
    to_year: Optional[int] = None
    language: Optional[str] = None
    include_cast: Optional[List[str]] = None
    limit: int = 20

class TopByActorParams(BaseModel):
    actor: str
    limit: int = 15

class SimilarParams(BaseModel):
    title: str
    limit: int = 15

class PlaylistParams(BaseModel):
    target_minutes: int = 480
    prefer_high_rating: bool = True
    genres: Optional[List[str]] = None
    language: Optional[str] = None

# Funciones bellacas para realizar las acciones joven y moderna
def do_search(p: SearchParams) -> List[Dict[str, Any]]:
    return search_title(p.query, p.limit)

def do_details(p: DetailParams) -> Optional[Dict[str, Any]]:
    return get_details_by_title(p.title)

def do_recommend(p: RecommendParams) -> List[Dict[str, Any]]:
    return recommend_movies(p.genres, p.min_vote, p.from_year, p.to_year, p.language, p.include_cast, p.limit)

def do_top_by_actor(p: TopByActorParams) -> List[Dict[str, Any]]:
    return top_movies_by_actor(p.actor, p.limit)

def do_similar(p: SimilarParams) -> List[Dict[str, Any]]:
    return similar_by_keywords(p.title, p.limit)

def do_playlist(p: PlaylistParams) -> Dict[str, Any]:
    return build_playlist(p.target_minutes, p.prefer_high_rating, p.genres, p.language)

# Configuración del servidor MCP con herramientas de películas
mcp = FastMCP("mcp-movielens")

MOVIE_TOOL_TIMEOUT = float(os.getenv("MOVIE_TOOL_TIMEOUT", "25.0"))

async def _run(fn, *args, timeout: Optional[float] = None):
    to = timeout if timeout is not None else MOVIE_TOOL_TIMEOUT
    return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=to)

# Herramientas que resuelven
@mcp.tool()
async def search_movie(params: SearchParams) -> List[Dict[str, Any]]:
    """Full-text search over titles; returns brief metadata sorted by rating/popularity."""
    return await _run(do_search, params)

@mcp.tool()
async def movie_details(params: DetailParams) -> Dict[str, Any]:
    """Exact/best-match details for a title; includes cast, crew (Director/Writer) and keywords when available."""
    res = await _run(do_details, params)
    return res or {}

@mcp.tool()
async def recommend_movies_tool(params: RecommendParams) -> List[Dict[str, Any]]:
    """Multi-filter recommender: genres, min_vote, year range, language, include_cast."""
    return await _run(do_recommend, params)

@mcp.tool()
async def top_movies_by_actor_tool(params: TopByActorParams) -> List[Dict[str, Any]]:
    """Top rated/popular films for a given actor name."""
    return await _run(do_top_by_actor, params)

@mcp.tool()
async def similar_movies_tool(params: SimilarParams) -> List[Dict[str, Any]]:
    """Keyword-overlap similarity to a given title."""
    return await _run(do_similar, params)

@mcp.tool()
async def build_playlist_tool(params: PlaylistParams) -> Dict[str, Any]:
    """Greedy watchlist fill to target_minutes using runtime; optional genres/language; bias toward rating/popularity."""
    return await _run(do_playlist, params)

if __name__ == "__main__":
    mcp.run()
