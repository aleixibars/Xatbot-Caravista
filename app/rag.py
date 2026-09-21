"""RAG core: embed, search, answer.

No Flask imports — this module must be callable and unit-testable without an
HTTP request (see CODING_STANDARDS.md).
"""

from __future__ import annotations

import json
from typing import Any, cast

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from app import config, db

# Minimum cosine score for a Qdrant hit to be treated as relevant.
# Lowered from 0.32 for issue #32: after #28's chunking fix a live test still
# missed content that verbatim exists in correctly-bounded fragments, so the
# floor — not chunk boundaries — was dropping them. With
# text-embedding-3-small, a short question against a list-heavy paragraph in
# the same language typically lands around 0.25-0.45 even when clearly
# relevant, so 0.32 cut into the relevant band. 0.25 keeps a floor under the
# unrelated tail (usually ≤ 0.2) without excluding borderline-but-correct
# fragments.
SEARCH_MIN_SCORE: float = 0.25

DISCLAIMER: str = (
    "\n\n---\n"
    "Això és informació general, no una resposta personalitzada al teu cas. "
    "Confirma-ho amb el nostre equip abans de prendre cap decisió."
)

# Shown (with the disclaimer) when no knowledge-base fragment matches.
NO_CONTEXT_MESSAGE: str = (
    "No he trobat informació sobre la teva pregunta. Contacta amb el nostre "
    "equip i t'ajudaran encantats."
)

SYSTEM_PROMPT: str = (
    "Ets l'assistent virtual de Caravista. Respon SEMPRE en el mateix idioma "
    "que la pregunta de l'usuari (català, castellà, anglès...). Ajudes els "
    "clients i visitants a resoldre dubtes sobre l'empresa i els seus serveis "
    "(què fem, per a qui, com contactar-nos, horaris, equip). Respon NOMÉS amb "
    "la informació del CONTEXT proporcionat. Si la resposta no és al CONTEXT, "
    "digues que no ho saps i ofereix contactar amb l'equip. No inventis mai "
    "dades de contacte, preus, terminis ni condicions. Mantén un to proper i "
    "informatiu i no presentis mai la resposta com un compromís contractual "
    "definitiu. NO escriguis mai cap frase final de descàrrec de "
    "responsabilitat, avís o matís del tipus «això és informació general, no "
    "una resposta personalitzada» — l'aplicació ja afegeix l'avís oficial "
    "després de la teva resposta, i qualsevol frase així teva seria redundant."
)

# Labels whose answers could plausibly resemble guidance/advice — only these
# get DISCLAIMER appended (issue #49). company_info/team_members/services are
# pure facts (hours, people, service list) where the disclaimer is noise;
# routing_rules/faq/rag carry escalation guidance and narrative content that
# genuinely borders on a commitment to the customer.
_ADVICE_ADJACENT_LABELS: frozenset[str] = frozenset({"routing_rules", "faq", "rag"})

# Valid router outputs, in the order route() scans for them inside the model's
# response: the five SQL tables first, "rag" deliberately last so it can only
# win when no SQL label appears anywhere in the response (a substring match on
# "rag" must never shadow a more specific label).
_ROUTER_LABELS: tuple[str, ...] = (
    "company_info",
    "team_members",
    "services",
    "routing_rules",
    "faq",
    "rag",
)

ROUTER_PROMPT: str = (
    "Classifica la pregunta de l'usuari segons quina font és més probable que "
    "la respongui. Respon EXACTAMENT amb una d'aquestes paraules i res més:\n"
    "- company_info: dades de contacte, adreça, telèfon, horaris, xarxes "
    "socials, web i dades generals de l'empresa\n"
    "- team_members: qui hi treballa, persones, departaments, preguntes sobre "
    "una persona concreta o buscar algú pel nom o pel càrrec/funció\n"
    "- services: quins serveis o productes ofereix l'empresa\n"
    "- routing_rules: amb quin departament o persona cal parlar per un tema\n"
    "- faq: preguntes freqüents sobre el funcionament de l'empresa\n"
    "- rag: qualsevol altra pregunta sobre Caravista i els seus serveis"
)


# Lazily-constructed clients, cached at module level. Kept behind getters so
# tests can patch them without any real network client being built at import.
_openai: OpenAI | None = None
_deepseek: OpenAI | None = None
_qdrant: QdrantClient | None = None
_collection_ready: bool = False


def _openai_client() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=config.OPENAI_API_KEY)
    return _openai


def _deepseek_client() -> OpenAI:
    global _deepseek
    if _deepseek is None:
        _deepseek = OpenAI(
            api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL
        )
    return _deepseek


def _qdrant_client() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY)
    return _qdrant


def _ensure_collection() -> None:
    """Create the Qdrant collection if it doesn't exist. Never recreate."""
    global _collection_ready
    if _collection_ready:
        return
    client = _qdrant_client()
    if not client.collection_exists(config.QDRANT_COLLECTION):
        client.create_collection(
            collection_name=config.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=config.EMBED_DIMS, distance=Distance.COSINE),
        )
    _collection_ready = True


def embed(text: str) -> list[float]:
    """Embed ``text`` with the configured OpenAI embedding model."""
    resp = _openai_client().embeddings.create(model=config.EMBED_MODEL, input=text)
    return resp.data[0].embedding


# Fragments are smaller and more numerous since the heading-level chunking of
# issue #28, so retrieve a few more candidates; SEARCH_MIN_SCORE still drops
# the irrelevant tail. Raised 8 → 10 for issue #32 so a relevant fragment
# ranked just outside the top 8 still reaches the score filter.
def search(query: str, limit: int = 10) -> list[dict]:
    """Retrieve the most relevant knowledge-base fragments for ``query``.

    Embeds the query, queries Qdrant, keeps hits scoring at least
    ``SEARCH_MIN_SCORE``, and returns their payloads.
    """
    _ensure_collection()
    vector = embed(query)
    result = _qdrant_client().query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=vector,
        limit=limit,
        with_payload=True,
    )
    fragments: list[dict] = []
    for point in result.points:
        if point.score is None or point.score < SEARCH_MIN_SCORE:
            continue
        payload = point.payload or {}
        fragments.append({"text": payload.get("text", ""), "source": payload.get("source", "")})
    return fragments


def route(question: str) -> str:
    """Classify ``question`` as one SQL table label or ``"rag"`` (ADR-0003).

    Any response with no recognisable label — or a failed router call — falls
    back to ``"rag"``: a bad classification must never raise, and the vector
    search must stay reachable even if the extra router call errors. Both
    fallback paths log to stdout so they're visible in production (issue #19).
    """
    try:
        resp = _deepseek_client().chat.completions.create(
            model=config.CHAT_MODEL,
            messages=cast(
                Any,
                [
                    {"role": "system", "content": ROUTER_PROMPT},
                    {"role": "user", "content": question},
                ],
            ),
            max_tokens=20,
        )
    except Exception as exc:
        print(
            json.dumps({"event": "router_fallback", "reason": "exception", "error": repr(exc)}),
            flush=True,
        )
        return "rag"
    response = (resp.choices[0].message.content or "").strip().lower()
    # Contains-match, not equality: chat models routinely wrap the label in a
    # few words of preamble or punctuation ("La resposta és: company_info").
    for candidate in _ROUTER_LABELS:
        if candidate in response:
            return candidate
    print(
        json.dumps(
            {"event": "router_fallback", "reason": "no_label_in_response", "response": response}
        ),
        flush=True,
    )
    return "rag"


# Core contact facts appended to every CONTEXT sent to the chat model: a
# routing_rules answer will otherwise fabricate a plausible-looking phone
# number, because that label's context carries no contact data. Always
# providing the real facts removes the opportunity to invent them, which is
# more robust than instructing the model not to. Keys absent from the seed are
# simply absent from the block (see app/db_seed.py).
_CONTACT_KEYS: tuple[str, ...] = ("phone_main", "whatsapp", "hours_mon_thu", "hours_fri")


def _contact_context() -> str:
    """Flat text rendering of the core contact company_info rows.

    The contact block is an enhancement, so a failed lookup must never break
    the answer — in particular the ``rag`` route worked without the SQLite DB
    before issue #41 and must keep working if it is unavailable. Same
    never-raise-and-log contract as :func:`route` (issue #19).
    """
    try:
        return "\n".join(
            f"{r['key']}: {r['value']}" for r in db.get_company_info(list(_CONTACT_KEYS))
        )
    except Exception as exc:
        print(
            json.dumps({"event": "contact_context_fallback", "error": repr(exc)}),
            flush=True,
        )
        return ""


def _sql_context(label: str, question: str) -> str:
    """Flat text rendering of the matching table's rows; empty if no row."""
    if label == "company_info":
        return "\n".join(f"{r['key']}: {r['value']}" for r in db.get_company_info())
    if label == "team_members":
        return "\n".join(
            f"{r['name']} — {r['role']} ({r['department']})"
            for r in db.search_team(question)
        )
    if label == "services":
        return "\n".join(
            f"{r['name']}: {r['one_liner']} ({r['url']})" for r in db.list_services()
        )
    if label == "routing_rules":
        return "\n".join(
            f"Àrea {r['area']}: {r['bot_action']}"
            for r in db.match_routing_rule(question)
        )
    if label == "faq":
        return "\n\n".join(
            f"Pregunta: {r['question']}\nResposta: {r['answer']}"
            for r in db.search_faq(question)
        )
    return ""


def answer(question: str, history: list[dict] | None = None) -> str:
    """Answer ``question`` grounded in retrieved context.

    Per ADR-0003: route to the SQLite structured data first; if the router
    says ``rag`` or the table lookup finds nothing, fall through to the
    vector search. ``services`` is special (issue #25): its table always has
    rows but only carries one-liners, so the vector search runs as well and
    any fragments are appended below the SQL rows.

    The disclaimer is appended only for advice-adjacent labels (issue #49,
    see ``_ADVICE_ADJACENT_LABELS``) and for the no-context fallback (which
    directs the user to a human — exactly the disclaimer's purpose). A fact
    label that falls through to the vector search is relabelled ``rag`` so
    its narrative answer keeps the disclaimer too.
    """
    label = route(question)
    context = _sql_context(label, question) if label != "rag" else ""
    if label == "services" and context:
        fragments = search(question)
        if fragments:
            context += "\n\n---\n\n" + "\n\n".join(f["text"] for f in fragments)
    if not context:
        fragments = search(question)
        if not fragments:
            return NO_CONTEXT_MESSAGE + DISCLAIMER
        context = "\n\n".join(f["text"] for f in fragments)
        # A fact label whose table matched nothing answers from the same
        # narrative KB fragments as "rag" — the disclaimer follows the
        # content, not the router's guess (issue #49).
        label = "rag"
    # Issue #41: whatever route produced the context, always add the real
    # contact facts so the model never has to invent a phone number when it
    # (naturally) offers a way to reach the firm.
    contact = _contact_context()
    if contact:
        context += "\n\n---\n\nContacte:\n" + contact
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": f"CONTEXT:\n{context}\n\nPregunta: {question}"})

    resp = _deepseek_client().chat.completions.create(
        model=config.CHAT_MODEL,
        messages=cast(Any, messages),
    )
    disclaimer = DISCLAIMER if label in _ADVICE_ADJACENT_LABELS else ""
    return (resp.choices[0].message.content or "") + disclaimer
