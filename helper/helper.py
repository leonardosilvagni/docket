#!/usr/bin/env python3
"""Vikunja inbox helper: meeting notes -> suggested tickets -> approved tickets.

1. Watches NOTES_DIR for new meeting notes (.md / .txt), e.g. OpenWhispr's
   disk-mirror folder.
2. Sends each new note to a local LLM (LM Studio, OpenAI-compatible API) and
   asks for action items with a title and a description.
3. Creates them in Vikunja's "Inbox" project, column "Suggested", labelled
   "AI suggested". The description says which project it should go to.
4. When you drag a card to "Approved", it is moved to that project (its default
   column, e.g. To Do). "Rejected" is the Inbox's done column, so rejected cards
   are simply marked done.

Standard library only. Settings come from environment variables (see .env).
"""
import hashlib, html, json, os, re, sys, time, urllib.error, urllib.request
from datetime import date, datetime
from pathlib import Path

VIKUNJA = os.environ.get("VIKUNJA_URL", "http://127.0.0.1").rstrip("/") + "/api/v1"
TOKEN = os.environ.get("VIKUNJA_TOKEN", "")
LLM = os.environ.get("LLM_URL", "http://127.0.0.1:1234/v1").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "qwen3.5-9b")
# 1 = always reason first; 0 = never; auto = reason within a budget, and if the budget runs out,
# finish from that reasoning without reasoning further (bounded time, nothing thrown away)
THINK = os.environ.get("LLM_THINKING", "auto").strip().lower()
CONTEXT = int(os.environ.get("LLM_CONTEXT", "32768"))  # context length to load the model with (0 = leave to LM Studio)
THINK_BUDGET = int(os.environ.get("LLM_THINK_BUDGET", "2500"))  # max tokens (reasoning + answer) in auto mode
OWNER = os.environ.get("OWNER", "the person who owns these notes")
LLM_KEY = os.environ.get("LLM_API_KEY", "")  # only if LM Studio's server requires an API token
NOTES = Path(os.environ.get("NOTES_DIR", "/notes"))
STATE = Path(os.environ.get("STATE_FILE", "/state/processed.json"))
POLL = int(os.environ.get("POLL_SECONDS", "60"))
SETTLE = int(os.environ.get("SETTLE_SECONDS", "60"))  # wait until a note stops changing
MAX_TRIES = int(os.environ.get("MAX_TRIES", "2"))  # attempts per note before giving up
PROCESS_EXISTING = os.environ.get("PROCESS_EXISTING", "0") == "1"
INBOX, LABEL = "Inbox", "AI suggested"
COLUMNS = ["Suggested", "Approved", "Rejected"]
PROJECT_RE = re.compile(r"Suggested project:\s*(?:<[^>]+>)*\s*([^<\n]+?)\s*(?:<|$)", re.I)


def log(*a):
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def http(method, url, body=None, headers=None, timeout=30):
    req = urllib.request.Request(url, method=method, headers={"Content-Type": "application/json", **(headers or {})},
                                 data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        txt = r.read().decode()
        return json.loads(txt) if txt else None


def api(method, path, body=None):
    return http(method, VIKUNJA + path, body, {"Authorization": f"Bearer {TOKEN}"})


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# ---------------------------------------------------------------- Vikunja setup
class Board:
    def __init__(self):
        projects = api("GET", "/projects?per_page=200") or []
        inbox = next((p for p in projects if p["title"] == INBOX and not p.get("is_archived")), None)
        if not inbox:
            inbox = api("PUT", "/projects", {"title": INBOX, "description": "<p>Tickets suggested from meeting notes. Drag to Approved or Rejected.</p>"})
            log("created project", INBOX)
        self.pid = inbox["id"]
        views = api("GET", f"/projects/{self.pid}/views")
        self.view = next(v for v in views if v.get("view_kind") in ("kanban", 3))
        self.vid = self.view["id"]
        buckets = api("GET", f"/projects/{self.pid}/views/{self.vid}/buckets") or []
        aliases = {"Suggested": {"suggested", "todo", "backlog"}, "Approved": {"approved", "doing", "inprogress"}, "Rejected": {"rejected", "done"}}
        self.cols, used = {}, set()
        for c in COLUMNS:
            b = next((b for b in buckets if b["id"] not in used and norm(b["title"]) == norm(c)), None) \
                or next((b for b in buckets if b["id"] not in used and norm(b["title"]) in aliases[c]), None)
            if b:
                used.add(b["id"])
                if b["title"] != c:
                    api("POST", f"/projects/{self.pid}/views/{self.vid}/buckets/{b['id']}", {**b, "title": c})
                self.cols[c] = b["id"]
            else:
                self.cols[c] = api("PUT", f"/projects/{self.pid}/views/{self.vid}/buckets",
                                   {"title": c, "project_view_id": self.vid})["id"]
        if self.view.get("done_bucket_id") != self.cols["Rejected"] or self.view.get("default_bucket_id") != self.cols["Suggested"]:
            self.view.update(done_bucket_id=self.cols["Rejected"], default_bucket_id=self.cols["Suggested"])
            api("POST", f"/projects/{self.pid}/views/{self.vid}", self.view)
        labels = api("GET", "/labels?per_page=200") or []
        lab = next((l for l in labels if l["title"] == LABEL), None) or api("PUT", "/labels", {"title": LABEL, "hex_color": "8e44ad"})
        self.label = lab["id"]
        log(f"Inbox ready (project {self.pid}, columns {self.cols})")

    def projects(self):
        return {p["title"]: p["id"] for p in (api("GET", "/projects?per_page=200") or [])
                if p["id"] != self.pid and not p.get("is_archived") and p["id"] > 0}

    def column_tasks(self, col):
        data = api("GET", f"/projects/{self.pid}/views/{self.vid}/tasks?per_page=200") or []
        if data and "tasks" in data[0]:  # kanban views return buckets with their tasks
            return next((b.get("tasks") or [] for b in data if b["id"] == self.cols[col]), [])
        return [t for t in data if t.get("bucket_id") == self.cols[col]]

    def open_titles(self):
        """Titles of open tasks, to skip duplicate suggestions. Best effort: never blocks a note."""
        out, page = set(), 1
        try:
            while page <= 20:
                batch = api("GET", f"/tasks/all?per_page=50&page={page}") or []
                out |= {norm(t["title"]) for t in batch if not t.get("done")}
                if len(batch) < 50:
                    break
                page += 1
        except urllib.error.HTTPError as e:
            log(f"  could not list existing tasks for duplicate check (HTTP {e.code}); continuing without it")
        return out


# ---------------------------------------------------------------- LLM
SCHEMA = {"type": "object", "properties": {"tasks": {"type": "array", "items": {"type": "object", "properties": {
    "title": {"type": "string"}, "description": {"type": "string"}, "project": {"type": "string"},
    "priority": {"type": "integer", "minimum": 0, "maximum": 4},
    "due_date": {"type": ["string", "null"]}}, "required": ["title", "description", "project", "priority", "due_date"]}}},
    "required": ["tasks"]}


def ensure_model_loaded():
    """Make sure exactly one copy of the model is loaded, with CONTEXT tokens, and return
    the name to send requests to. Requests must use the loaded copy's exact id: otherwise
    LM Studio loads a second copy on demand (with its small default context)."""
    if not CONTEXT:
        return MODEL
    base = re.sub(r"/v1/?$", "", LLM)
    auth = {"Authorization": f"Bearer {LLM_KEY}"} if LLM_KEY else None
    try:
        models = http("GET", base + "/api/v1/models", headers=auth)
        models = models.get("models", models.get("data", [])) if isinstance(models, dict) else models

        def names(m):
            ids = {m.get(k) for k in ("key", "id", "model_key", "display_name") if m.get(k)}
            return ids | {i.split("/")[-1] for i in ids}  # "qwen/qwen3.5-9b" also matches "qwen3.5-9b"

        m = next((m for m in models if MODEL in names(m)), None)
        if m is None:
            log(f"  model {MODEL} not found in LM Studio's model list; using it as is (check LLM_MODEL against lms ls)")
            return MODEL
        instances = m.get("loaded_instances") or []
        ctx = lambda i: (i.get("config") or {}).get("context_length", 0)
        keep = next((i for i in sorted(instances, key=ctx, reverse=True) if ctx(i) >= CONTEXT), None)
        for inst in instances:  # one copy only: unload duplicates and too-small copies
            if inst is not keep:
                log(f"  unloading extra copy {inst['id']} ({ctx(inst)} tokens of context)")
                http("POST", base + "/api/v1/models/unload", {"instance_id": inst["id"]}, auth)
        if keep:
            return keep["id"]
        log(f"  loading {MODEL} with {CONTEXT} tokens of context ...")
        key = m.get("key") or m.get("id") or MODEL
        r = http("POST", base + "/api/v1/models/load", {"model": key, "context_length": CONTEXT}, auth, timeout=600) or {}
        return r.get("instance_id") or key
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise
        log(f"  could not set the context length automatically (HTTP {e.code}); LM Studio will use its default")
        return MODEL


def extract(note, name, meeting_date, projects):
    system = (
        f"You turn meeting notes into action-item tickets for {OWNER} (the notes' owner).\n"
        "Rules:\n"
        "- Only action items that were actually stated or clearly agreed. Never invent tasks, owners or dates.\n"
        "- title: short imperative, max 80 characters (e.g. 'Order 5-0 sutures for Sept 29 surgery').\n"
        "- description: 1-4 sentences: what exactly to do, the context/why, specifics mentioned (people, quantities, places), "
        "and when it counts as done.\n"
        f"- project: exactly one of {json.dumps(sorted(projects))}, or 'Unsorted' if unclear.\n"
        "- priority: 0 unset, 1 low, 2 medium, 3 high, 4 urgent. Use 0 unless urgency was discussed.\n"
        f"- due_date: YYYY-MM-DD only if a deadline was stated; resolve relative dates against the meeting date {meeting_date}. Otherwise null.\n"
        "- Merge duplicates. If there are no action items, return an empty list.\n"
        f"- Every action item is for {OWNER}, no matter who said it or who volunteered. Never write an owner and never "
        "try to work out which speaker is who: list every task that was agreed in the meeting, and the owner will sort them later.\n"
        "'Today' means the meeting date; 'this week' means no fixed date unless a day is named; 'before <event>' means the event's date.\n"
        "This is a simple extraction task. Reason briefly (a few short lines): list the action items once, assign dates, then answer. "
        "Do not deliberate, re-check or rewrite the list.")
    # timestamps like "[03:21] " add tokens and nothing else
    text = re.sub(r"(?m)^\[\d{1,2}:\d{2}(?::\d{2})?\]\s*", "", note)[:30000]

    use_model = ensure_model_loaded()

    def ask(think, limit=None, draft=""):
        user = f"Meeting note '{name}' ({meeting_date}):\n\n{text}"
        if draft:  # continue from the reasoning done so far instead of starting over
            user += ("\n\nYour analysis so far (it was cut off, so finish it quickly):\n" + draft[-12000:] +
                     "\n\nNow give the final answer.")
        body = {"model": use_model, "temperature": 0.2,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": ("" if think else "/no_think\n") + user}],
                "response_format": {"type": "json_schema", "json_schema": {"name": "tickets", "strict": True, "schema": SCHEMA}}}
        if not think:
            body.update(chat_template_kwargs={"enable_thinking": False}, reasoning_effort="none")
        if limit:
            body["max_tokens"] = limit
        r = http("POST", LLM + "/chat/completions", body, {"Authorization": f"Bearer {LLM_KEY}"} if LLM_KEY else None, timeout=1800)
        choice = r["choices"][0]
        txt = re.sub(r"<think>.*?</think>", "", choice["message"].get("content") or "", flags=re.S).strip()
        txt = txt[txt.find("{"): txt.rfind("}") + 1]
        try:
            return json.loads(txt).get("tasks", []), None
        except ValueError:
            msg = choice["message"]
            reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
            if not reasoning:
                m = re.search(r"<think>(.*)", msg.get("content") or "", flags=re.S)
                reasoning = m.group(1) if m else ""
            ask.draft = reasoning
            return None, f"finish_reason={choice.get('finish_reason')}, tokens={r.get('usage', {})}"

    if THINK in ("0", "off", "no", "false"):
        tasks, why = ask(False)
    elif THINK in ("1", "on", "yes", "true"):
        tasks, why = ask(True)
    else:  # auto
        tasks, why = ask(True, THINK_BUDGET)
        if tasks is None:
            log(f"  reasoning ran past {THINK_BUDGET} tokens; continuing from it without further reasoning")
            tasks, why = ask(False, draft=getattr(ask, "draft", ""))
    if tasks is None:
        raise RuntimeError(f"model returned no usable answer ({why}). If finish_reason is 'length', "
                           "raise the context length for this model in LM Studio (My Models > model settings).")
    return tasks


# ---------------------------------------------------------------- work
def load_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return None


def save_state(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=1))
    tmp.replace(STATE)


def notes():
    for p in sorted(NOTES.rglob("*")):
        if p.is_file() and p.suffix.lower() in (".md", ".txt") and not p.name.startswith("."):
            yield p


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def meeting_date(p):
    m = re.search(r"(20\d\d-\d\d-\d\d)", p.name)
    return m.group(1) if m else date.fromtimestamp(p.stat().st_mtime).isoformat()


def process_note(board, p):
    text = p.read_text(errors="replace").strip()
    if len(text) < 40:
        return 0
    projects = board.projects()
    existing = board.open_titles()
    log(f"note {p.name}: asking {MODEL} ...")
    tasks = extract(text, p.name, meeting_date(p), projects)
    made = 0
    for t in tasks:
        title = t["title"].strip()[:250]
        if not title or norm(title) in existing:
            continue
        proj = t["project"] if t["project"] in projects else "Unsorted"
        desc = (f"<p>{html.escape(t['description'].strip())}</p>"
                f"<p>Suggested project: <strong>{html.escape(proj)}</strong></p>"
                f"<p><em>From meeting note: {html.escape(p.name)} ({meeting_date(p)}). Edit the project name above to send it elsewhere.</em></p>")
        due = t.get("due_date")
        if due and not re.fullmatch(r"\d{4}-\d\d-\d\d", due):
            due = None
        task = api("PUT", f"/projects/{board.pid}/tasks", {
            "title": title, "description": desc, "priority": max(0, min(4, int(t.get("priority") or 0))),
            "due_date": f"{due}T17:00:00Z" if due else None})
        api("PUT", f"/tasks/{task['id']}/labels", {"label_id": board.label})
        existing.add(norm(title))
        made += 1
        log(f"  suggested: {title}  -> {proj}")
    return made


def move_approved(board):
    projects = {k.lower(): v for k, v in board.projects().items()}
    for t in board.column_tasks("Approved"):
        m = PROJECT_RE.search(t.get("description") or "")
        target = projects.get(m.group(1).strip().lower()) if m else None
        if not target:
            if "could not move" not in (t.get("description") or "").lower():
                full = api("GET", f"/tasks/{t['id']}")
                full["description"] = (full.get("description") or "") + \
                    "<p><strong>Could not move: set 'Suggested project' to an existing project name.</strong></p>"
                api("POST", f"/tasks/{t['id']}", full)
                log(f"  approved but no valid project: {t['title']}")
            continue
        full = api("GET", f"/tasks/{t['id']}")
        full["project_id"] = target
        full.pop("bucket_id", None)
        full.pop("buckets", None)
        d = re.sub(r"<p><em>From meeting note:.*?Edit the project name above to send it elsewhere\.</em></p>", "", full.get("description") or "")
        full["description"] = re.sub(r"<p><strong>Could not move:.*?</strong></p>", "", d)
        api("POST", f"/tasks/{t['id']}", full)
        log(f"  approved -> moved: {t['title']}")


def main():
    if not TOKEN:
        sys.exit("VIKUNJA_TOKEN is not set (see .env).")
    drain = "--drain" in sys.argv  # one immediate pass over all pending notes, then exit
    settle = 0 if drain else SETTLE
    board = None
    state = load_state()
    while True:
        try:
            board = board or Board()
            if state is None:  # first run: don't flood the inbox with old notes
                state = {} if PROCESS_EXISTING else {str(p): digest(p) for p in notes()}
                save_state(state)
                log(f"first run: {len(state)} existing note(s) marked as already seen")
            now = time.time()
            for p in notes():
                if now - p.stat().st_mtime < settle:
                    continue
                h = digest(p)
                if state.get(str(p)) == h:
                    continue
                fails = state.get(str(p) + "#failed", {})
                if fails.get("hash") == h and fails.get("count", 0) >= MAX_TRIES:
                    continue  # gave up on this version of the note; edit the note to retry
                try:
                    n = process_note(board, p)
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    raise  # connection problems: retry later without counting
                except Exception as e:
                    c = fails.get("count", 0) + 1 if fails.get("hash") == h else 1
                    state[str(p) + "#failed"] = {"hash": h, "count": c}
                    save_state(state)
                    log(f"note {p.name}: attempt {c}/{MAX_TRIES} failed: {type(e).__name__}: {e}")
                    if c >= MAX_TRIES:
                        log(f"note {p.name}: giving up. Fix the cause, then edit or touch the note to retry.")
                    continue
                state[str(p)] = h
                state.pop(str(p) + "#failed", None)
                save_state(state)
                log(f"note {p.name}: {n} ticket(s) suggested")
            move_approved(board)
            if drain:
                log("drain finished")
                return
        except urllib.error.HTTPError as e:
            log(f"HTTP {e.code} {e.url}: {e.read().decode()[:300]}")
            board = None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if drain:
                log(f"connection problem ({e}); notes will be processed next time")
                sys.exit(1)
            log(f"connection problem ({e}); retrying in 30s")
            board = None
            time.sleep(30)
            continue
        except Exception as e:  # keep the service alive
            log(f"error: {type(e).__name__}: {e}")
        if drain:
            sys.exit(1)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
