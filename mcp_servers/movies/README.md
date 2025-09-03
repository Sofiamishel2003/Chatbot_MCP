# MCP – Recomendador y Buscador de Películas (MovieLens/TMDB)

Servidor **MCP** (Model Context Protocol) que expone herramientas para buscar, describir, recomendar y armar playlists de películas a partir de archivos CSV locales. El servidor se conecta por **STDIO** a clientes compatibles (p. ej. MCP Inspector, editores o LLMs que soporten MCP).

> **Estado del repo y datasets**
>
> En este repositorio ya existe la carpeta `datasets/` con:
>
> - `movies_metadata.csv` ✅
> - `keywords.csv` ✅
>
> **No incluye** `credits.csv` porque excede el tamaño permitido por GitHub.
> Las herramientas que requieren reparto/equipo funcionarán **solo** si el usuario descarga ese archivo y lo coloca en `datasets/` (ver la sección **Datasets externos**).

---

## 1) ¿Qué puedes hacer con este servidor?
- **Búsqueda por título** con ranking por votos y popularidad.
- **Ficha detallada** de una película (metadata general).  
- **Recomendaciones** con filtros por género, idioma, rango de años y calificación mínima.
- **Similares por keywords** (películas relacionadas por palabras clave).
- **Playlist** para completar un objetivo de minutos totales usando `runtime`.

> Cuando `credits.csv` está presente, se activan filtros y vistas adicionales por **reparto** y **equipo (Director/Writer/Screenplay)**.

---

## 2) Herramientas MCP expuestas

| Tool | Para qué sirve | Depende de |
|---|---|---|
| `search_movie` | Buscar títulos y devolver metadata condensada | `movies_metadata.csv` |
| `movie_details` | Ficha detallada (y **cast/crew** si hay `credits.csv`) + keywords | `movies_metadata.csv`, `keywords.csv`, *(opcional)* `credits.csv` |
| `recommend_movies_tool` | Recomendador multi-filtro (géneros, idioma, años, calificación) y **include_cast** si hay `credits.csv` | `movies_metadata.csv`, *(opcional)* `credits.csv` |
| `top_movies_by_actor_tool` | Mejores películas por actor/actriz | **Requiere** `credits.csv` |
| `similar_movies_tool` | Películas similares por intersección de keywords | `movies_metadata.csv`, `keywords.csv` |
| `build_playlist_tool` | Lista de reproducción para alcanzar X minutos (greedy por `runtime`) | `movies_metadata.csv` |

### Qué funciona sin `credits.csv`
- `search_movie`, `recommend_movies_tool` (sin `include_cast`), `similar_movies_tool`, `build_playlist_tool` y la parte **básica** de `movie_details` (sin cast/crew).

### Qué requiere `credits.csv`
- `top_movies_by_actor_tool` y el filtro `include_cast` en `recommend_movies_tool`.  
- `movie_details` mostrará **cast/crew** solo si `credits.csv` está disponible.

---

## 3) Datasets externos (cómo obtener `credits.csv`)

Para habilitar todas las funciones basadas en reparto/equipo, descarga el dataset completo desde Kaggle (autor **Rounak Banik**):

- **The Movies Dataset (Kaggle)**: https://www.kaggle.com/datasets/rounakbanik/the-movies-dataset/data

Coloca el archivo `credits.csv` dentro de `datasets/`:
```
Movies_ChatBot/
├── movie_server.py
├── movie_sources.py
├── requirements_movies.txt
└── datasets/
    ├── movies_metadata.csv
    ├── keywords.csv
    └── credits.csv   ← (opcional pero recomendado)
```

> El cargador normaliza tipos (incluido `id`) y convierte cadenas JSON con comillas simples a JSON válido para poder cruzar tablas sin problemas.

---

## 4) Instalación rápida
Requisitos: **Python 3.10+**, `pip`

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -r requirements_movies.txt
pip install mcp[cli]
```

---

## 5) Ejecución por STDIO (MCP)

### Opción A: MCP Inspector
1) Transport: **STDIO**  
2) Command: `python` (o `py` en Windows)  
3) Arguments: `movie_server.py stdio`  
4) Working directory: carpeta del proyecto  
5) Conectar y verificar en la pestaña **Tools** que aparezcan las funciones.

### Opción B: Línea de comandos rápida
```bash
python movie_server.py stdio
```
Configura tu host MCP para comunicarse por STDIO con el proceso anterior
---

## 6) Ejemplos de prueba (útiles para capturas)

**a) search_movie**
```json
{"query":"Toy Story","limit":5}
```

**b) movie_details** (sin `credits.csv` verás solo metadata general + keywords; con `credits.csv` también cast/crew)
```json
{"title":"Inception"}
```

**c) recommend_movies_tool** (sin cast)
```json
{
  "genres": ["Science Fiction","Adventure"],
  "min_vote": 7.5,
  "from_year": 2000,
  "to_year": 2020,
  "language": "en",
  "limit": 10
}
```

**d) similar_movies_tool**
```json
{"title":"The Dark Knight","limit":10}
```

**e) build_playlist_tool**
```json
{"target_minutes":480,"prefer_high_rating":true,"genres":["Drama","Thriller"]}
```

**f) (requiere `credits.csv`) top_movies_by_actor_tool**
```json
{"actor":"Tom Hanks","limit":8}
```

**g) (requiere `credits.csv`) recommend_movies_tool con include_cast**
```json
{
  "genres": ["Drama"],
  "min_vote": 7.0,
  "include_cast": ["Leonardo DiCaprio"],
  "limit": 10
}
```

---

## 7) Documentación en la que me basé
- **MCP Python SDK** (documentación y ejemplos de servidores MCP):  
  https://github.com/modelcontextprotocol/python-sdk

---

## 8) Referencias
- **The Movies Dataset — Rounak Banik (Kaggle)**:  
  https://www.kaggle.com/datasets/rounakbanik/the-movies-dataset/data
- **GroupLens / MovieLens** y **TMDB** (orígenes de los datos).  
  “This product uses the TMDB API but is not endorsed or certified by TMDB.”
