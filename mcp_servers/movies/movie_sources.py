
import os, glob, json
from functools import lru_cache
from typing import Dict, Any, List, Optional, Tuple, Iterable, Set
import pandas as pd

# ---------- Cargador de archivos ----------
def _find(path_like: str) -> Optional[str]:
    patterns = [path_like, path_like + ".csv", path_like + "*.csv"]
    for p in patterns:
        for g in glob.glob(p):
            return g
    return None

def _resolve_default_paths() -> Dict[str, Optional[str]]:
    roots = []
    roots.append(os.path.join(os.path.dirname(__file__), "datasets"))
    names = [
        "movies_metadata", "credits", "keywords",
        "links", "links_small", "ratings_small"
    ]
    out = {n: None for n in names}
    for root in roots:
        for n in names:
            if out[n] is None:
                cand = _find(os.path.join(root, n))
                if cand:
                    out[n] = cand
    return out

PATHS = _resolve_default_paths()

# ---------- Cached loaders ----------
@lru_cache(maxsize=1)
def load_movies() -> pd.DataFrame:
    path = PATHS.get("movies_metadata")
    if not path:
        return pd.DataFrame()
    df = pd.read_csv(path, low_memory=False)
    # Normalizar las columnas
    for col in ("budget","revenue","vote_count","vote_average","popularity"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "release_date" in df.columns:
        df["release_year"] = pd.to_datetime(df["release_date"], errors="coerce").dt.year
    else:
        df["release_year"] = None
    # Genres/production_countries/languages may be JSON-like; try parsing lists of dicts
    def parse_jsonish(x):
        try:
            if pd.isna(x): return []
            return json.loads(x.replace("'", '"'))
        except Exception:
            return []
    for jscol in ("genres","production_countries","production_companies","spoken_languages"):
        if jscol in df.columns:
            df[jscol] = df[jscol].apply(parse_jsonish)
    # Title lowercase helper
    df["title_lc"] = df["title"].astype(str).str.strip().str.lower()
    return df

@lru_cache(maxsize=1)
def load_credits() -> pd.DataFrame:
    path = PATHS.get("credits")
    if not path: return pd.DataFrame()
    df = pd.read_csv(path)
    # parse cast/crew JSON-like
    def parse_jsonish(x):
        try:
            if pd.isna(x): return []
            return json.loads(x.replace("'", '"'))
        except Exception:
            return []
    for col in ("cast","crew"):
        if col in df.columns:
            df[col] = df[col].apply(parse_jsonish)
    return df

@lru_cache(maxsize=1)
def load_keywords() -> pd.DataFrame:
    path = PATHS.get("keywords")
    if not path: return pd.DataFrame()
    df = pd.read_csv(path)
    def parse_jsonish(x):
        try:
            if pd.isna(x): return []
            return json.loads(x.replace("'", '"'))
        except Exception:
            return []
    if "keywords" in df.columns:
        df["keywords"] = df["keywords"].apply(parse_jsonish)
    return df

@lru_cache(maxsize=1)
def load_ratings_small() -> pd.DataFrame:
    path = PATHS.get("ratings_small")
    if not path: return pd.DataFrame()
    df = pd.read_csv(path)
    return df

# ---------- Helper search ----------
def _norm_genres(genres_list: List[Dict[str, Any]]) -> List[str]:
    return [g.get("name","").strip() for g in (genres_list or []) if isinstance(g, dict) and g.get("name")]

def search_title(q: str, limit: int = 10) -> List[Dict[str, Any]]:
    m = load_movies()
    if m.empty: return []
    qlc = (q or "").strip().lower()
    if not qlc: return []
    sub = m[m["title_lc"].str.contains(qlc, na=False)].copy()
    sub = sub.sort_values(["vote_count","vote_average","popularity"], ascending=False).head(limit)
    return [movie_row_to_dict(r) for _, r in sub.iterrows()]

def movie_row_to_dict(r: pd.Series) -> Dict[str, Any]:
    return {
        "id": int(r["id"]) if str(r.get("id","")).isdigit() else r.get("id"),
        "imdb_id": r.get("imdb_id"),
        "title": r.get("title"),
        "overview": r.get("overview"),
        "genres": _norm_genres(r.get("genres", [])) if isinstance(r.get("genres"), list) else r.get("genres"),
        "release_date": r.get("release_date"),
        "release_year": int(r["release_year"]) if pd.notna(r.get("release_year")) else None,
        "runtime": float(r["runtime"]) if pd.notna(r.get("runtime")) else None,
        "vote_average": float(r["vote_average"]) if pd.notna(r.get("vote_average")) else None,
        "vote_count": int(r["vote_count"]) if pd.notna(r.get("vote_count")) else None,
        "popularity": float(r["popularity"]) if pd.notna(r.get("popularity")) else None,
        "original_language": r.get("original_language"),
        "adult": bool(r.get("adult")) if r.get("adult") in (True, False) else False,
        "poster_path": r.get("poster_path"),
        "backdrop_path": r.get("backdrop_path"),
    }

def get_details_by_title(title: str) -> Optional[Dict[str, Any]]:
    m = load_movies()
    if m.empty: return None
    sub = m[m["title_lc"] == (title or "").strip().lower()]
    if sub.empty:
        # try contains best match
        sub = m[m["title_lc"].str.contains((title or "").strip().lower(), na=False)].head(1)
        if sub.empty:
            return None
    r = sub.iloc[0]
    det = movie_row_to_dict(r)
    # join credits
    c = load_credits()
    if not c.empty and "id" in c.columns:
        cc = c[c["id"] == r["id"]]
        if not cc.empty:
            det["cast"] = [p.get("name") for p in cc.iloc[0]["cast"]][:15]
            det["crew"] = [p.get("name") + " (" + p.get("job","") + ")" for p in cc.iloc[0]["crew"] if p.get("job") in ("Director","Writer","Screenplay")]
    # keywords
    k = load_keywords()
    if not k.empty and "id" in k.columns and "keywords" in k.columns:
        kk = k[k["id"] == r["id"]]
        if not kk.empty:
            det["keywords"] = [d.get("name") for d in kk.iloc[0]["keywords"]]
    return det

# ---------- Sistema de recomendación potente ----------
def recommend_movies(genres: Optional[List[str]] = None,
                     min_vote: float = 0.0,
                     from_year: Optional[int] = None,
                     to_year: Optional[int] = None,
                     language: Optional[str] = None,
                     include_cast: Optional[List[str]] = None,
                     limit: int = 20) -> List[Dict[str, Any]]:
    m = load_movies()
    if m.empty: return []
    df = m.copy()

    # Filter by years
    if from_year is not None:
        df = df[df["release_year"].fillna(0) >= from_year]
    if to_year is not None:
        df = df[df["release_year"].fillna(9999) <= to_year]

    # Language
    if language:
        df = df[df["original_language"].astype(str).str.lower() == language.lower()]

    # Genres filter (any overlap)
    if genres:
        genres_lc = {g.lower() for g in genres}
        def has_any(gs):
            names = [d.get("name","").lower() for d in (gs or []) if isinstance(d, dict)]
            return any(n in genres_lc for n in names)
        if "genres" in df.columns:
            df = df[df["genres"].apply(has_any)]

    # Cast filter
    if include_cast:
        cast_lc = {c.lower() for c in include_cast}
        c = load_credits()
        if not c.empty:
            # explode cast names
            def cast_names(lst):
                return [p.get("name","") for p in (lst or []) if isinstance(p, dict)]
            c2 = c[["id","cast"]].copy()
            c2["cast_names"] = c2["cast"].apply(cast_names)
            # filter rows whose cast includes any target name
            c2["has"] = c2["cast_names"].apply(lambda names: any(name.lower() in cast_lc for name in names))
            ids = set(c2[c2["has"]]["id"].tolist())
            df = df[df["id"].isin(ids)]

    # Score and rank
    df = df[(df["vote_average"].fillna(0) >= min_vote)]
    df = df.sort_values(["vote_average","vote_count","popularity"], ascending=False).head(limit)
    return [movie_row_to_dict(r) for _, r in df.iterrows()]

def top_movies_by_actor(actor: str, limit: int = 15) -> List[Dict[str, Any]]:
    c = load_credits()
    m = load_movies()
    if c.empty or m.empty: return []
    actor_lc = (actor or "").strip().lower()

    def in_cast(lst):
        return any((p.get("name","").strip().lower() == actor_lc) for p in (lst or []) if isinstance(p, dict))

    ids = c[c["cast"].apply(in_cast)]["id"].tolist()
    df = m[m["id"].isin(ids)].copy()
    if df.empty: return []
    df = df.sort_values(["vote_average","vote_count","popularity"], ascending=False).head(limit)
    return [movie_row_to_dict(r) for _, r in df.iterrows()]

def similar_by_keywords(title: str, limit: int = 15) -> List[Dict[str, Any]]:
    m = load_movies()
    k = load_keywords()
    if m.empty or k.empty: return []
    ref = m[m["title_lc"] == (title or "").strip().lower()]
    if ref.empty: return []
    ref_id = ref.iloc[0]["id"]
    kk = k.set_index("id")
    if ref_id not in kk.index: return []
    ref_kw = {d.get("name","").lower() for d in kk.loc[ref_id,"keywords"] if isinstance(d, dict)}
    if not ref_kw: return []

    # Build overlap score for others
    scores = []
    for mid, row in kk.iterrows():
        if mid == ref_id: continue
        words = {d.get("name","").lower() for d in row["keywords"] if isinstance(d, dict)}
        inter = ref_kw & words
        if inter:
            scores.append((mid, len(inter)))
    if not scores: return []
    top_ids = [mid for mid, sc in sorted(scores, key=lambda t: t[1], reverse=True)[:limit]]
    sub = m[m["id"].isin(top_ids)].copy()
    # preserve order
    sub["__ord"] = sub["id"].apply(lambda x: top_ids.index(x) if x in top_ids else 999999)
    sub = sub.sort_values("__ord").drop(columns="__ord")
    return [movie_row_to_dict(r) for _, r in sub.iterrows()]

def build_playlist(target_minutes: int = 480, prefer_high_rating: bool = True,
                   genres: Optional[List[str]] = None, language: Optional[str] = None) -> Dict[str, Any]:
    m = load_movies()
    if m.empty: return {"minutes": 0, "items": []}
    df = m.copy()
    if genres:
        genres_lc = {g.lower() for g in genres}
        def has_any(gs):
            names = [d.get("name","").lower() for d in (gs or []) if isinstance(d, dict)]
            return any(n in genres_lc for n in names)
        if "genres" in df.columns:
            df = df[df["genres"].apply(has_any)]
    if language:
        df = df[df["original_language"].astype(str).str.lower() == language.lower()]
    if prefer_high_rating:
        df = df.sort_values(["vote_average","vote_count"], ascending=False)
    else:
        df = df.sort_values("popularity", ascending=False)

    total = 0; items = []
    for _, r in df.iterrows():
        rt = r.get("runtime")
        try:
            rt = float(rt)
        except Exception:
            rt = None
        if not rt or rt <= 0:
            continue
        if total + rt > target_minutes:
            continue
        items.append(movie_row_to_dict(r))
        total += rt
        if total >= target_minutes * 0.95:
            break
    return {"minutes": int(total), "count": len(items), "items": items}
